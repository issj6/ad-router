from fastapi import APIRouter, Request, HTTPException, Response
from typing import Any, Dict
import uuid
import time
import datetime

from ..config import CONFIG
from ..db import get_session
from ..models import RequestLog
from ..schemas import APIResponse
from ..services.router import find_upstream_config, get_adapter_config, choose_route, should_throttle_callback, find_matching_rule
from ..services.connector import http_send_with_retry
from ..mapping_dsl import eval_expr, render_template, eval_body_template
from ..utils.logger import info, debug, warning, error, perf_info
from sqlalchemy import select, text
import re
import urllib.parse

router = APIRouter()


def _normalize_event_key(raw: str) -> str:
    """将事件名做宽松清洗用于匹配：小写、去空白、去 -/_。"""
    if raw is None:
        return ""
    return re.sub(r'[-_\s]+', '', str(raw).strip().lower())

# 废弃：不再使用硬编码猜测式归一化；保留占位避免外部引用报错
def _normalize_event_name(raw_event_name: str) -> str:  # pragma: no cover
    return str(raw_event_name or "")

def _apply_upstream_event_mapping(udm: Dict[str, Any], inbound_adapter: Dict[str, Any] | None) -> None:
    """
    使用上游配置中的 event_name_map 对 udm.event.name 进行显式映射。
    不返回值，直接修改传入的 udm。
    """
    if not inbound_adapter:
        return
    event_map = (inbound_adapter or {}).get("event_name_map") or {}
    if not isinstance(event_map, dict) or not event_map:
        return
    try:
        original = (udm.get("event") or {}).get("name")
        key = _normalize_event_key(original)
        norm_map = { _normalize_event_key(k): v for k, v in event_map.items() }
        mapped = norm_map.get(key)
        if mapped:
            udm.setdefault("meta", {})["original_event_name"] = original
            udm.setdefault("event", {})["name"] = str(mapped)
    except Exception as e:
        warning(f"Failed to apply upstream event mapping: {e}")

def _should_callback_and_remap_event(udm: Dict[str, Any], routing_udm: Dict[str, Any], config: Dict[str, Any]) -> tuple[bool, str | None]:
    """
    基于链接级 rule 的 callback_events 进行白名单判定与（可选）事件名改写。
    返回 (should_callback, remapped_event_name)
    - 若不应回调，返回 (False, None)
    - 若应回调，且需要改写事件名，则返回 (True, new_name)
    - 若应回调，但无需改写，返回 (True, None)
    """
    rule = find_matching_rule(routing_udm, config)
    whitelist = (rule or {}).get("callback_events")
    if not whitelist:
        return False, None

    current_event = (udm.get("event") or {}).get("name")
    if current_event is None:
        return False, None

    # 支持两种形态：
    # 1) dict: {src_event: dst_event} → 命中且可改名
    # 2) list/tuple/set: [eventA, eventB] → 仅白名单，不改名
    normalized_current = _normalize_event_key(current_event)

    if isinstance(whitelist, dict):
        normalized_map = { _normalize_event_key(k): v for k, v in whitelist.items() }
        mapped_value = normalized_map.get(normalized_current)
        if mapped_value is None:
            return False, None
        return True, str(mapped_value)

    if isinstance(whitelist, (list, tuple, set)):
        normalized_set = { _normalize_event_key(x) for x in whitelist }
        if normalized_current in normalized_set:
            return True, None  # 不改名
        return False, None

    # 支持字符串简写：callback_events: REGISTERED
    if isinstance(whitelist, str):
        if normalized_current == _normalize_event_key(whitelist):
            return True, None
        return False, None

    # 其他类型：不支持
    return False, None


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
            warning(f"Failed to map field {udm_path}: {e}")

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
        error(f"Signature verification failed: {e}")
        return False




@router.get("/cb", response_model=APIResponse)
async def handle_upstream_callback(request: Request, response: Response):
    trace_id = str(uuid.uuid4())

    # 读取 rid
    rid = request.query_params.get("rid")
    if not rid:
        response.status_code = 500
        return APIResponse(success=False, code=500, message="Missing rid")

    # 全局路由开关：关闭时直接对上游返回200，不回拨下游
    try:
        global_enabled = bool(CONFIG.get("settings", {}).get("routes", {}).get("enabled", True))
    except Exception:
        global_enabled = True
    if not global_enabled:
        return APIResponse(success=True, code=200, message="ok")

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
                    debug(f"Failed to extract callback_template from upload_params: {e}")
                    callback_template = None
    except Exception as e:
        warning(f"Failed to load request_log by rid: {e}")

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
                        warning(f"Callback signature verification failed for upstream {up_id}")
                        response.status_code = 500
                        return APIResponse(success=False, code=500, message="Invalid signature")
                # 映射
                field_map = inbound_adapter.get("field_map", {})
                udm = _map_inbound_fields(field_map, ctx, secrets)

    # 使用上游配置的事件映射（替代旧的硬编码归一化）
    if inbound_adapter and (udm.get("event", {}).get("name") is not None):
        _apply_upstream_event_mapping(udm, inbound_adapter)

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
        warning(f"Failed to get throttle rate for rid {rid}: {e}")
        throttle_rate = 0.0

    # 如果token里没有带回调模板，可按需从数据库查（此处先尝试用token里的）
    if not callback_template:
        # 简化：不查库，直接走下游配置兜底
        pass

    # 链接级白名单判定与可选事件名改写
    should_callback, remapped = _should_callback_and_remap_event(udm, routing_udm, CONFIG)
    if not should_callback:
        # 未命中白名单：仅保存，不回调
        try:
            async with await get_session() as session:
                res = await session.execute(select(RequestLog).where(RequestLog.rid == rid))
                obj = res.scalar_one_or_none()
                if obj:
                    callback_params = {"query": query_params, "body": body_data}
                    obj.callback_params = callback_params
                    obj.downstream_url = None
                    obj.is_callback_sent = 4  # 未命中白名单，明确区分于历史默认值0
                    obj.callback_event_type = (udm.get("event") or {}).get("name")
                    await session.commit()
                else:
                    warning(f"RequestLog not found to set callback skip fields, rid={rid}")
        except Exception as e:
            error(f"Failed to update downstream fields on whitelist skip: {e}")
        return APIResponse(success=True, code=200, message="ok")

    # 命中白名单：可选改写事件名
    if remapped is not None:
        udm.setdefault("event", {})["name"] = remapped

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
            warning(f"apply_macros failed: {e}")

    # 自定义日志：打印最终回拨下游URL
    perf_info(f"[to-downstream] callback url: {final_downstream_url}")

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
                warning(f"RequestLog not found to set downstream_url, rid={rid}")
    except Exception as e:
        error(f"Failed to update downstream fields: {e}")

    # 如果命中扣量，直接返回200给上游，不转发给下游
    if should_throttle:
        info(f"[throttle] callback throttled, rid={rid}, throttle_rate={throttle_rate}")
        
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
            error(f"Failed to update throttle status: {e}")
        
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
                            warning(f"RequestLog not found to set callback_sent, rid={rid}")
                except Exception as e:
                    error(f"Failed to update callback_sent: {e}")
        else:
            # 无模板则视为无回调需求（直接成功）
            downstream_status, downstream_response = 200, {"msg": "no_callback_template"}

        # 以HTTP状态对齐
        if downstream_status == 200:
            return APIResponse(success=True, code=200, message="ok")
        else:
            # 已尝试向下游发送但返回非200，标记为回拨失败(3)
            try:
                if final_downstream_url:
                    async with await get_session() as session:
                        res = await session.execute(select(RequestLog).where(RequestLog.rid == rid))
                        obj = res.scalar_one_or_none()
                        if obj:
                            obj.is_callback_sent = 3
                            from datetime import datetime, timezone, timedelta
                            shanghai_tz = timezone(timedelta(hours=8))
                            obj.callback_time = datetime.now(shanghai_tz).strftime("%Y-%m-%d %H:%M:%S")
                            await session.commit()
            except Exception as e:
                error(f"Failed to update callback failure status: {e}")
            return APIResponse(success=False, code=500, message="server_config_error")

    except Exception as e:
        error(f"Error dispatching to downstream: {e}")
        # 出现异常且存在下游URL，视为回拨失败(3)
        try:
            if 'final_downstream_url' in locals() and final_downstream_url:
                async with await get_session() as session:
                    res = await session.execute(select(RequestLog).where(RequestLog.rid == rid))
                    obj = res.scalar_one_or_none()
                    if obj:
                        obj.is_callback_sent = 3
                        from datetime import datetime, timezone, timedelta
                        shanghai_tz = timezone(timedelta(hours=8))
                        obj.callback_time = datetime.now(shanghai_tz).strftime("%Y-%m-%d %H:%M:%S")
                        await session.commit()
        except Exception as ex:
            error(f"Failed to update callback failure status on exception: {ex}")
        return APIResponse(success=False, code=500, message="server_error")
