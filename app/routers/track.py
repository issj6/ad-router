from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Any, Dict
import uuid
import time
import datetime
import logging
import urllib.parse

from ..config import CONFIG
from ..db import get_session
from ..models import EventLog, DispatchLog
from ..schemas import TrackRequest, APIResponse
from ..services.router import choose_route, find_upstream_config, get_adapter_config
from ..services.connector import http_send_with_retry
from ..mapping_dsl import render_template, eval_body_template
from ..utils.security import generate_callback_token
from sqlalchemy.exc import IntegrityError

router = APIRouter()

def _today() -> str:
    """获取今日日期字符串 YYYYMMDD"""
    return datetime.datetime.now().strftime("%Y%m%d")

def _make_udm(body: TrackRequest, request: Request, up_id: str = None, ds_id: str = None) -> Dict[str, Any]:
    """构造统一数据模型(UDM)"""
    # 默认使用13位毫秒时间戳
    now = int(time.time() * 1000)
    
    return {
        "event": {
            "type": body.event_type
        },
        "click": {
            "id": body.click_id,
            "source": ds_id or body.ds_id
        },
        "ad": {
            "ad_id": body.ad_id
        },
        "device": body.device or {},
        "user": body.user or {},
        "net": {
            "ip": body.ip or (request.client.host if request.client else ""),
            "ua": body.ua or request.headers.get("user-agent", "")
        },
        "time": {
            "ts": body.ts or now
        },
        "meta": {
            "downstream_id": ds_id or body.ds_id,
            "upstream_id": up_id,
            "ext": body.ext or {}
        }
    }

async def _save_event_log(trace_id: str, udm: Dict[str, Any], body: TrackRequest, callback_template: str | None = None):
    """保存事件日志"""
    day = _today()
    
    try:
        async with await get_session() as session:
            event_log = EventLog(
                day=day,
                trace_id=trace_id,
                ds_id=udm["meta"]["downstream_id"],
                up_id=udm["meta"]["upstream_id"],
                event_type=udm["event"]["type"],
                click_id=udm["click"]["id"],
                ad_id=udm["ad"]["ad_id"],
                ts=udm["time"]["ts"],
                ip=udm["net"]["ip"],
                ua=udm["net"]["ua"],
                payload={
                    "device": body.device,
                    "user": body.user,
                    "ext": body.ext,
                    "callback_template": callback_template
                }
            )
            
            session.add(event_log)
            await session.commit()
            
    except IntegrityError:
        # 幂等：当日内 (ds_id,event_type,click_id) 重复上报，忽略冲突
        logging.info("duplicate event ignored (idempotent)")
    except Exception as e:
        # 其它数据库错误不影响主流程，但要记录日志
        logging.error(f"Failed to save event log: {e}")

async def _dispatch_to_upstream(trace_id: str, udm: Dict[str, Any], upstream_config: Dict[str, Any],
                               event_type: str, callback_template: str | None = None) -> tuple[int, Any]:
    """分发到上游"""
    # 获取适配器配置
    adapter = get_adapter_config(upstream_config, "outbound", event_type)
    if not adapter:
        logging.warning(f"No outbound adapter for upstream {upstream_config['id']} event {event_type}")
        return 200, {"msg": "no_adapter"}
    
    # 准备上下文
    ctx = {
        "udm": udm,
        "body": udm,  # 兼容性
        "meta": {
            "ip": udm["net"]["ip"],
            "ua": udm["net"]["ua"]
        }
    }
    
    secrets = upstream_config.get("secrets", {})
    
    # 准备回调URL助手
    app_secret = CONFIG["settings"]["app_secret"]
    callback_base = CONFIG["settings"]["callback_base"].rstrip("/")
    
    def cb_url():
        # 新规则：用 rid=trace_id 关联，不再使用 token；保留下游模板的原始查询串
        base = f"{callback_base}/cb?rid={trace_id}"
        try:
            if callback_template:
                from urllib.parse import urlparse
                parsed = urlparse(callback_template)
                if parsed.query:
                    return f"{base}&{parsed.query}"
        except Exception:
            pass
        return base
    
    helpers = {"cb_url": cb_url}  # 将回调模板通过token传递到回调环节
    
    # 渲染URL
    url = render_template(adapter["url"], adapter.get("macros", {}), ctx, secrets, helpers)
    # logging.info(f"[to-upstream] click url: {url}")
    method = adapter.get("method", "GET")
    headers = adapter.get("headers")
    
    # 处理请求体（如果有）
    body_template = adapter.get("body")
    body_data = None
    if body_template:
        body_data = eval_body_template(body_template, ctx, secrets, helpers)
    
    # 发送请求
    timeout_ms = adapter.get("timeout_ms", 5000)
    retry_config = adapter.get("retry", {})
    max_retries = retry_config.get("max", 1)
    backoff_ms = retry_config.get("backoff_ms", 200)
    
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
                direction="to_upstream",
                partner_id=upstream_config["id"],
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

@router.get("/v1/track", response_model=APIResponse)
async def track_event(request: Request,
                     ds_id: str,
                     event_type: str,
                     click_id: str = None,
                     ad_id: str = None,
                     ts: int = None,
                     ip: str = None,
                     ua: str = None,
                     # 设备信息
                     device_os: str = None,
                     device_model: str = None,
                     device_idfa: str = None,
                     device_caid: str = None,
                     device_oaid: str = None,
                     device_imei: str = None,
                     device_android_id: str = None,
                     os_version: str = None,
                     device_mac: str = None,
                     # 用户信息
                     user_phone_md5: str = None,
                     user_email_sha256: str = None,
                     # 扩展字段
                     ext_custom_id: str = None,
                     # 回调模板（下游提供，必须URL编码）
                     callback: str | None = None):
    """
    统一事件上报接口
    支持的事件类型：click, imp, event
    """
    # 验证事件类型
    if event_type not in ["click", "imp"]:
        raise HTTPException(status_code=400, detail="Invalid event_type")

    # 生成链路追踪ID
    trace_id = str(uuid.uuid4())

    # 组装 device / user / ext
    device = {}
    if device_os: device["os"] = device_os
    if device_model: device["model"] = device_model
    if device_idfa: device["idfa"] = device_idfa
    if device_caid: device["caid"] = device_caid
    if device_oaid: device["oaid"] = device_oaid
    if device_imei: device["imei"] = device_imei
    if device_android_id: device["android_id"] = device_android_id
    if os_version: device["os_version"] = os_version
    if device_mac: device["mac"] = device_mac

    user = {}
    if user_phone_md5: user["phone_md5"] = user_phone_md5
    if user_email_sha256: user["email_sha256"] = user_email_sha256

    ext = {}
    if ext_custom_id: ext["custom_id"] = ext_custom_id

    # 构造与原POST一致的请求体模型
    body = TrackRequest(
        ds_id=ds_id,
        event_type=event_type,
        ad_id=ad_id,
        click_id=click_id,
        ts=ts,
        ip=ip,
        ua=ua,
        device=device or None,
        user=user or None,
        ext=ext or None
    )

    # 解析并保存下游回调模板（URL编码→解码后保存）
    callback_template: str | None = None
    if callback:
        try:
            callback_template = urllib.parse.unquote(callback)
        except Exception:
            callback_template = callback


    # 构造初始UDM用于路由
    udm_for_routing = _make_udm(body, request)

    # 路由选择
    up_id, ds_out = choose_route(udm_for_routing, CONFIG)

    # 构造最终UDM
    udm = _make_udm(body, request, up_id, body.ds_id)

    # 保存事件日志（异步，不阻塞主流程）
    # 将callback模板一并保存到事件日志的payload中
    if callback_template is not None:
        if "ext" not in udm["meta"] or udm["meta"]["ext"] is None:
            udm["meta"]["ext"] = {}
    # 保存事件日志（异步，不阻塞主流程）
    await _save_event_log(trace_id, udm, body, callback_template)
    
    # 准备响应数据
    # 如果没有找到上游，直接认为成功（我们已记录）
    if not up_id:
        return APIResponse(success=True, code=200, message="ok")

    # 查找上游配置
    upstream_config = find_upstream_config(up_id, CONFIG)
    if not upstream_config:
        return APIResponse(success=True, code=200, message="ok")

    # 分发到上游
    try:
        upstream_status, upstream_response = await _dispatch_to_upstream(
            trace_id, udm, upstream_config, event_type, callback_template
        )

        # 200 认为成功；其它按HTTP对齐
        if upstream_status == 200:
            return APIResponse(success=True, code=200, message="ok")
        else:
            return APIResponse(success=False, code=upstream_status, message="upstream_error")

    except Exception as e:
        logging.error(f"Error dispatching to upstream: {e}")
        return APIResponse(success=False, code=500, message="server_error")
