from fastapi import APIRouter, Request, HTTPException
from typing import Any, Dict
import uuid
import time
import datetime
import logging

from ..config import CONFIG
from ..db import get_session
from ..models import RequestLog
from ..schemas import APIResponse
from ..services.router import find_upstream_config, get_adapter_config
from ..services.connector import http_send_with_retry
from ..mapping_dsl import eval_expr, render_template, eval_body_template
from sqlalchemy import select, text
import re
import urllib.parse

router = APIRouter()


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
async def handle_upstream_callback(request: Request):
    trace_id = str(uuid.uuid4())

    # 读取 rid
    rid = request.query_params.get("rid")
    if not rid:
        raise HTTPException(status_code=400, detail="Missing rid")

    # 注意：上游ID/下游ID 可以不从token取，按 inbound 映射后如需写日志可从UDM取；此处保持最小改动
    up_id = ""
    ds_id = ""
    click_id = None
    callback_template = None

    # 根据 rid 从统一表获取上下文（原始模板已不再保存在新表中，这里仅尝试获取 ds_id/up_id/click_id）
    try:
        async with await get_session() as session:
            stmt = select(RequestLog).where(RequestLog.rid == rid)
            res = await session.execute(stmt)
            row = res.scalar_one_or_none()
            if row:
                ds_id = row.ds_id or ""
                up_id = row.up_id or ""
                click_id = row.click_id or None
                # 从统一表的上报原始参数中恢复下游回调模板
                try:
                    upload = row.upload_params or {}
                    callback_template = upload.get("callback_template")
                except Exception:
                    callback_template = callback_template
    except Exception as e:
        logging.warning(f"Failed to load request_log by rid: {e}")

    # 解析请求参数
    query_params = dict(request.query_params)

    try:
        body_data = await request.json()
    except Exception:
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
                        raise HTTPException(status_code=400, detail="Invalid signature")
                # 映射
                field_map = inbound_adapter.get("field_map", {})
                udm = _map_inbound_fields(field_map, ctx, secrets)

    # 补充上下文信息
    udm.setdefault("meta", {})
    udm.setdefault("click", {})
    udm["meta"]["upstream_id"] = up_id
    udm["meta"]["downstream_id"] = ds_id
    if click_id:
        udm["click"]["id"] = click_id

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
            return mapping.get(key, m.group(0))

        return re.sub(r"__([A-Za-z0-9_]+)__", rep, tmpl)

    final_downstream_url: str | None = None
    if callback_template:
        try:
            final_downstream_url = apply_macros(callback_template, build_macro_map(udm))
        except Exception as e:
            logging.warning(f"apply_macros failed: {e}")

    # 自定义日志：打印最终回拨下游URL
    logging.info(f"[to-downstream] callback url: {final_downstream_url}")

    # 记录回调原始参数与最终回拨URL到统一表（使用ORM保存，便于调试）
    try:
        async with await get_session() as session:
            res = await session.execute(select(RequestLog).where(RequestLog.rid == rid))
            obj = res.scalar_one_or_none()
            if obj:
                obj.callback_params = {"query": query_params, "body": body_data}
                obj.downstream_url = final_downstream_url
                obj.is_callback_sent = 0
                obj.callback_event_type = (udm.get("event") or {}).get("name")
                await session.commit()
            else:
                logging.warning(f"RequestLog not found to set downstream_url, rid={rid}")
    except Exception as e:
        logging.error(f"Failed to update downstream fields: {e}")

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
            return APIResponse(success=False, code=downstream_status, message="downstream_error")

    except Exception as e:
        logging.error(f"Error dispatching to downstream: {e}")
        return APIResponse(success=False, code=500, message="server_error")
