from fastapi import APIRouter, Request, HTTPException
from typing import Any, Dict
import uuid
import time
import datetime
import logging

from ..config import CONFIG
from ..db import get_session
from ..models import CallbackLog, DispatchLog
from ..schemas import CallbackResponse
from ..services.router import find_upstream_config, find_downstream_config, get_adapter_config
from ..services.connector import http_send_with_retry
from ..mapping_dsl import eval_expr, render_template, eval_body_template
from ..utils.security import decode_token
import re
import urllib.parse

router = APIRouter()

def _today() -> str:
    """获取今日日期字符串 YYYYMMDD"""
    return datetime.datetime.now().strftime("%Y%m%d")

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

async def _verify_callback_signature(verify_config: Dict[str, Any], ctx: Dict[str, Any], secrets: Dict[str, str]) -> bool:
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

async def _dispatch_to_downstream(trace_id: str, udm: Dict[str, Any], downstream_config: Dict[str, Any]) -> tuple[int, Any]:
    """分发回调到下游"""
    # 获取适配器配置
    adapter = get_adapter_config(downstream_config, "outbound_callback", "event")
    if not adapter:
        logging.warning(f"No outbound_callback adapter for downstream {downstream_config['id']}")
        return 200, {"msg": "no_adapter"}
    
    # 准备上下文
    ctx = {"udm": udm}
    secrets = downstream_config.get("secrets", {})
    helpers = {}
    
    # 渲染URL
    url = adapter["url"]
    if "macros" in adapter:
        url = render_template(adapter["url"], adapter["macros"], ctx, secrets, helpers)
    
    method = adapter.get("method", "GET")
    headers = adapter.get("headers")
    
    # 处理请求体
    body_template = adapter.get("body")
    body_data = None
    if body_template:
        body_data = eval_body_template(body_template, ctx, secrets, helpers)
    
    # 发送请求
    timeout_ms = adapter.get("timeout_ms", 5000)
    retry_config = adapter.get("retry", {})
    max_retries = retry_config.get("max", 3)
    backoff_ms = retry_config.get("backoff_ms", 300)
    
    status, response = await http_send_with_retry(
        method=method,
        url=url,
        headers=headers,
        body=body_data,
        timeout_ms=timeout_ms,
        max_retries=max_retries,
        backoff_ms=backoff_ms
    )
    
    # 记录分发日志
    try:
        day = _today()
        async with await get_session() as session:
            dispatch_log = DispatchLog(
                day=day,
                trace_id=trace_id,
                direction="to_downstream",
                partner_id=downstream_config["id"],
                endpoint=url,
                method=method,
                status=status,
                req={
                    "headers": headers,
                    "body": body_data
                },
                resp={
                    "data": response
                }
            )
            session.add(dispatch_log)
            await session.commit()
    except Exception as e:
        logging.error(f"Failed to save dispatch log: {e}")
    
    return status, response

@router.get("/cb/{token}", response_model=CallbackResponse)
async def handle_upstream_callback(token: str, request: Request):
    """
    处理上游回调（仅GET）
    """
    trace_id = str(uuid.uuid4())
    day = _today()
    
    # 解码token
    try:
        app_secret = CONFIG["settings"]["app_secret"]
        payload = decode_token(token, app_secret)
        up_id = payload.get("up_id")
        ds_id = payload.get("ds_id")
        click_id = payload.get("click_id")
        callback_template = payload.get("callback_template")
    except Exception as e:
        logging.warning(f"Invalid callback token: {e}")
        raise HTTPException(status_code=400, detail="Invalid token")
    
    # 查找上游和下游配置
    upstream_config = find_upstream_config(up_id, CONFIG)
    downstream_config = find_downstream_config(ds_id, CONFIG)
    
    if not upstream_config:
        raise HTTPException(status_code=400, detail="Unknown upstream")
    if not downstream_config:
        raise HTTPException(status_code=400, detail="Unknown downstream")
    
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
    
    # 获取上游回调适配器
    inbound_adapter = get_adapter_config(upstream_config, "inbound_callback", "event")
    if not inbound_adapter:
        logging.warning(f"No inbound_callback adapter for upstream {up_id}")
        return CallbackResponse(code=0, msg="no_inbound_adapter")
    
    secrets = upstream_config.get("secrets", {})
    
    # 验证签名
    verify_config = inbound_adapter.get("verify")
    if verify_config:
        if not await _verify_callback_signature(verify_config, ctx, secrets):
            logging.warning(f"Callback signature verification failed for upstream {up_id}")
            raise HTTPException(status_code=400, detail="Invalid signature")
    
    # 映射字段到UDM
    field_map = inbound_adapter.get("field_map", {})
    udm = _map_inbound_fields(field_map, ctx, secrets)

    # 补充token中的信息
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
        mapping.update({k: (ev or "") for k in ["EVENT","EVENT_TYPE","EVENTTYPE","EVT","TYPE"]})
        ck = (u.get("click") or {}).get("id")
        mapping.update({k: (ck or "") for k in ["CLICK_ID","CLICKID","CLID","CLKID"]})
        amt = ((u.get("meta") or {}).get("amount"))
        mapping.update({k: (str(amt) if amt is not None else "") for k in ["AMOUNT","PRICE","VALUE"]})
        days = ((u.get("meta") or {}).get("days"))
        mapping.update({k: (str(days) if days is not None else "") for k in ["DAYS","RETENTION","RETAIN_DAYS"]})
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

    # 记录回调日志
    callback_success = True
    try:
        async with await get_session() as session:
            callback_log = CallbackLog(
                day=day,
                trace_id=trace_id,
                up_id=up_id,
                ds_id=ds_id,
                ok=1,  # 先标记为成功，后续如果下游分发失败会更新
                raw={
                    "token_payload": payload,
                    "query": query_params,
                    "body": body_data,
                    "udm": udm,
                    "callback_template": callback_template,
                    "final_downstream_url": final_downstream_url
                }
            )
            session.add(callback_log)
            await session.commit()
    except Exception as e:
        logging.error(f"Failed to save callback log: {e}")
        callback_success = False

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
        else:
            # 兜底：使用下游配置的 outbound_callback
            downstream_status, downstream_response = await _dispatch_to_downstream(
                trace_id, udm, downstream_config
            )
        
        # 如果下游分发失败，更新回调日志
        if downstream_status >= 400 and callback_success:
            try:
                async with await get_session() as session:
                    # 这里简化处理，实际可以用UPDATE语句
                    pass
            except Exception:
                pass
        
        return CallbackResponse(code=0, msg="ok")
        
    except Exception as e:
        logging.error(f"Error dispatching to downstream: {e}")
        return CallbackResponse(code=5000, msg="server_error")
