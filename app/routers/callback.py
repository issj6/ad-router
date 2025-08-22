from fastapi import APIRouter, Request, HTTPException, Response
from typing import Any, Dict
import uuid
import time
import datetime
import logging

from ..config import CONFIG
from ..db import get_session
from ..models import RequestLog
from ..schemas import APIResponse
from ..services.router import find_upstream_config, get_adapter_config, choose_route, should_throttle_callback
from ..services.connector import http_send_with_retry
from ..mapping_dsl import eval_expr, render_template, eval_body_template
from sqlalchemy import select, text
import re
import urllib.parse

router = APIRouter()


def _normalize_event_name(raw_event_name: str) -> str:
    """
    归一化事件名称为标准格式
    支持的标准事件：ACTIVATED, REGISTERED, PAID, RETAINED
    """
    if not raw_event_name:
        return ""
    
    # 清洗：转小写，去除空白，替换分隔符为空
    cleaned = re.sub(r'[-_\s]+', '', str(raw_event_name).strip().lower())
    
    # 映射字典
    event_mapping = {
        # 激活相关
        'activated': 'ACTIVATED',
        'activation': 'ACTIVATED', 
        'active': 'ACTIVATED',
        'act': 'ACTIVATED',
        'install': 'ACTIVATED',
        'installed': 'ACTIVATED',
        
        # 注册相关
        'register': 'REGISTERED',
        'registered': 'REGISTERED',
        'reg': 'REGISTERED',
        'signup': 'REGISTERED',
        'signUp': 'REGISTERED',
        
        # 付费相关
        'pay': 'PAID',
        'paid': 'PAID',
        'payment': 'PAID',
        'purchase': 'PAID',
        'buy': 'PAID',
        
        # 留存相关
        'retained': 'RETAINED',
        'retention': 'RETAINED',
        'retain': 'RETAINED'
    }
    
    # 查找匹配
    normalized = event_mapping.get(cleaned)
    if normalized:
        logging.debug(f"Event normalized: {raw_event_name} -> {normalized}")
        return normalized
    
    # 未匹配则保持原值，记录警告
    logging.warning(f"Unknown event type: {raw_event_name}, keeping original value")
    return raw_event_name


def _map_inbound_fields(field_map: Dict[str, str], ctx: Dict[str, Any], secrets: Dict[str, str]) -> Dict[str, Any]:
    """映射入站字段到UDM"""
    udm = {
        "event": {},
        "click": {},
        "ad": {},
        "device": {},
        "user": {},
        "net": {},
        "time": {},
        "meta": {}
    }

    for udm_path, expr in (field_map or {}).items():
        try:
            # 解析UDM路径，如 "udm.click.id"
            parts = udm_path.split(".")
            if len(parts) < 2 or parts[0] != "udm":
                continue

            # 计算表达式值
            value = eval_expr(expr, ctx, secrets, {})

            # 设置到UDM中
            current = udm
            for part in parts[1:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = value

        except Exception as e:
            logging.warning(f"Failed to map field {udm_path}: {e}")

    return udm


async def _verify_callback_signature(verify_config: Dict[str, Any], ctx: Dict[str, Any],
                                     secrets: Dict[str, str]) -> bool:
    """验证回调签名"""
    if not verify_config:
        return True  # 没有验证配置则跳过验证

    try:
        # 获取签名
        signature_expr = verify_config.get("signature", "")
        actual_sig = eval_expr(signature_expr, ctx, secrets, {})

        # 计算期望签名
        message_expr = verify_config.get("message", "")
        secret_ref = verify_config.get("secret_ref", "")

        message = eval_expr(message_expr, ctx, secrets, {})
        secret = secrets.get(secret_ref, "")

        if verify_config.get("type") == "hmac_sha256":
            import hmac
            import hashlib
            expected_sig = hmac.new(secret.encode(), str(message).encode(), hashlib.sha256).hexdigest()
            return str(actual_sig) == expected_sig

        return False

    except Exception as e:
        logging.error(f"Signature verification failed: {e}")
        return False




@router.get("/cb", response_model=APIResponse)
async def handle_upstream_callback(request: Request, response: Response):
    trace_id = str(uuid.uuid4())

    # 读取 rid
    rid = request.query_params.get("rid")
    if not rid:
        response.status_code = 500
        return APIResponse(success=False, code=500, message="Missing rid")

    # 注意：上游ID/下游ID 可以不从token取，按 inbound 映射后如需写日志可从UDM取；此处保持最小改动
    up_id = ""
    ds_id = ""

    callback_template = None

    # 根据 rid 从统一表获取上下文（原始模板已不再保存在新表中，这里仅尝试获取 ds_id/up_id）
    try:
        async with await get_session() as session:
            stmt = select(RequestLog).where(RequestLog.rid == rid)
            res = await session.execute(stmt)
            row = res.scalar_one_or_none()
            if row:
                ds_id = row.ds_id or ""
                up_id = row.up_id or ""
                # 从统一表的上报原始参数中恢复下游回调模板
                try:
                    upload = row.upload_params or {}
                    callback_template = upload.get("callback_template")
                except Exception as e:
                    logging.debug(f"Failed to extract callback_template from upload_params: {e}")
                    callback_template = None
    except Exception as e:
        logging.warning(f"Failed to load request_log by rid: {e}")

    # 解析请求参数
    query_params = dict(request.query_params)

    try:
        body_data = await request.json()
    except Exception:
        # 不是JSON body，这是正常的GET请求情况
        body_data = {}

    # 构造上下文
    ctx = {
        "query": query_params,
        "body": body_data,
        "meta": {
            "ip": request.client.host if request.client else "",
            "ua": request.headers.get("user-agent", "")
        }
    }

    # 如果缺少上游配置，则不进行 inbound 解析，直接走模板替换（宽松容错）
    udm = {"event": {}, "click": {}, "meta": {}}
    inbound_adapter = None

    if up_id:
        upstream_config = find_upstream_config(up_id, CONFIG)
        if upstream_config:
            inbound_adapter = get_adapter_config(upstream_config, "inbound_callback", "event")
            if inbound_adapter:
                secrets = upstream_config.get("secrets", {})
                # 验签
                verify_config = inbound_adapter.get("verify")
                if verify_config:
                    if not await _verify_callback_signature(verify_config, ctx, secrets):
                        logging.warning(f"Callback signature verification failed for upstream {up_id}")
                        response.status_code = 500
                        return APIResponse(success=False, code=500, message="Invalid signature")
                # 映射
                field_map = inbound_adapter.get("field_map", {})
                udm = _map_inbound_fields(field_map, ctx, secrets)

    # 事件名称归一化（在映射完成后，使用前进行）
    if udm.get("event", {}).get("name"):
        original_event = udm["event"]["name"]
        normalized_event = _normalize_event_name(original_event)
        udm["event"]["name"] = normalized_event
        # 保存原始事件名用于调试
        udm.setdefault("meta", {})["original_event_name"] = original_event

    # 补充上下文信息
    udm.setdefault("meta", {})
    udm.setdefault("click", {})
    udm["meta"]["upstream_id"] = up_id
    udm["meta"]["downstream_id"] = ds_id
    
    # 根据原始请求数据获取路由配置和扣量设置
    throttle_rate = 0.0  # 默认不扣量
    try:
        # 从数据库获取的信息重建 UDM 用于路由判断
        if row:
            # 构造用于路由判断的 UDM
            routing_udm = {
                "ad": {
                    "ad_id": row.ad_id,
                    "campaign_id": ""  # 这里可能需要从 upload_params 中获取
                },
                "meta": {
                    "downstream_id": row.ds_id
                }
            }
            
            # 尝试从上报参数中获取更多信息
            if row.upload_params and "query" in row.upload_params:
                query_data = row.upload_params["query"]
                if isinstance(query_data, dict):
                    ad_info = query_data.get("ad", {})
                    if isinstance(ad_info, dict):
                        routing_udm["ad"]["campaign_id"] = ad_info.get("campaign_id", "")
            
            # 获取路由配置和扣量设置
            _, _, route_enabled, throttle_rate = choose_route(routing_udm, CONFIG)
    except Exception as e:
        logging.warning(f"Failed to get throttle rate for rid {rid}: {e}")
        throttle_rate = 0.0

    # 如果token里没有带回调模板，可按需从数据库查（此处先尝试用token里的）
    if not callback_template:
        # 简化：不查库，直接走下游配置兜底
        pass

    # 若存在下游模板，则根据UDM做宏替换以得到最终URL
    def build_macro_map(u: Dict[str, Any]) -> Dict[str, str]:
        # 常见别名统一映射
        mapping = {}
        ev = (u.get("event") or {}).get("name")
        mapping.update({k: (ev or "") for k in ["EVENT", "EVENT_TYPE", "EVENTTYPE", "EVT", "TYPE"]})
        ck = (u.get("click") or {}).get("id")
        mapping.update({k: (ck or "") for k in ["CLICK_ID", "CLICKID", "CLID", "CLKID"]})
        amt = ((u.get("meta") or {}).get("amount"))
        mapping.update({k: (str(amt) if amt is not None else "") for k in ["AMOUNT", "PRICE", "VALUE"]})
        days = ((u.get("meta") or {}).get("days"))
        mapping.update({k: (str(days) if days is not None else "") for k in ["DAYS", "RETENTION", "RETAIN_DAYS"]})
        return mapping

    def apply_macros(tmpl: str, mapping: Dict[str, str]) -> str:
        def rep(m):
            key = m.group(1).upper()
            # 未匹配的占位符置空，避免"dirty URL"
            return mapping.get(key, "")

        return re.sub(r"__([A-Za-z0-9_]+)__", rep, tmpl)

    final_downstream_url: str | None = None
    if callback_template:
        try:
            final_downstream_url = apply_macros(callback_template, build_macro_map(udm))
        except Exception as e:
            logging.warning(f"apply_macros failed: {e}")

    # 自定义日志：打印最终回拨下游URL
    logging.info(f"[to-downstream] callback url: {final_downstream_url}")

    # 判断是否需要扣量
    should_throttle = should_throttle_callback(rid, throttle_rate)
    
    # 记录回调原始参数与最终回拨URL到统一表（使用ORM保存，便于调试）
    try:
        async with await get_session() as session:
            res = await session.execute(select(RequestLog).where(RequestLog.rid == rid))
            obj = res.scalar_one_or_none()
            if obj:
                callback_params = {"query": query_params, "body": body_data}
                obj.callback_params = callback_params
                obj.downstream_url = final_downstream_url
                obj.is_callback_sent = 0
                obj.callback_event_type = (udm.get("event") or {}).get("name")
                await session.commit()
            else:
                logging.warning(f"RequestLog not found to set downstream_url, rid={rid}")
    except Exception as e:
        logging.error(f"Failed to update downstream fields: {e}")

    # 如果命中扣量，直接返回200给上游，不转发给下游
    if should_throttle:
        logging.info(f"[throttle] callback throttled, rid={rid}, throttle_rate={throttle_rate}")
        
        # 更新数据库状态为扣量状态 (is_callback_sent = 2)
        try:
            async with await get_session() as session:
                res = await session.execute(select(RequestLog).where(RequestLog.rid == rid))
                obj = res.scalar_one_or_none()
                if obj:
                    obj.is_callback_sent = 2  # 设置为扣量状态
                    # 设置扣量时间
                    from datetime import datetime, timezone, timedelta
                    shanghai_tz = timezone(timedelta(hours=8))
                    obj.callback_time = datetime.now(shanghai_tz).strftime("%Y-%m-%d %H:%M:%S")
                    await session.commit()
        except Exception as e:
            logging.error(f"Failed to update throttle status: {e}")
        
        return APIResponse(success=True, code=200, message="ok")

    # 记录回调日志（已取消旧表，统一使用 request_log）
    callback_success = True

    # 分发到下游
    try:
        if final_downstream_url:
            # 直接按最终URL回调（GET）
            status, resp = await http_send_with_retry(
                method="GET",
                url=final_downstream_url,
                headers=None,
                body=None,
                timeout_ms=5000,
                max_retries=3,
                backoff_ms=300
            )
            downstream_status, downstream_response = status, resp

            # 回拨成功则更新统一表状态与时间
            if downstream_status == 200:
                try:
                    async with await get_session() as session:
                        res = await session.execute(select(RequestLog).where(RequestLog.rid == rid))
                        obj = res.scalar_one_or_none()
                        if obj:
                            obj.is_callback_sent = 1
                            # 格式化时间（上海时区）
                            from datetime import datetime, timezone, timedelta
                            shanghai_tz = timezone(timedelta(hours=8))
                            obj.callback_time = datetime.now(shanghai_tz).strftime("%Y-%m-%d %H:%M:%S")
                            await session.commit()
                        else:
                            logging.warning(f"RequestLog not found to set callback_sent, rid={rid}")
                except Exception as e:
                    logging.error(f"Failed to update callback_sent: {e}")
        else:
            # 无模板则视为无回调需求（直接成功）
            downstream_status, downstream_response = 200, {"msg": "no_callback_template"}

        # 以HTTP状态对齐
        if downstream_status == 200:
            return APIResponse(success=True, code=200, message="ok")
        else:
            return APIResponse(success=False, code=500, message="server_config_error")

    except Exception as e:
        logging.error(f"Error dispatching to downstream: {e}")
        return APIResponse(success=False, code=500, message="server_error")
