
from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import JSONResponse
from typing import Any, Dict
import uuid
import time
import datetime
import logging
import urllib.parse

from ..config import CONFIG
from ..db import get_session
from ..models import RequestLog
from ..schemas import TrackRequest, APIResponse
from ..services.router import choose_route, find_upstream_config, get_adapter_config
from ..services.connector import http_send_with_retry
from ..mapping_dsl import render_template, eval_body_template
from ..utils.security import generate_callback_token
from sqlalchemy.exc import IntegrityError


router = APIRouter()


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
            "ad_id": body.ad_id,
            "channel_id": body.channel_id
        },
        "device": body.device or {},
        "user": body.user or {},
        "net": {
            # 取消兜底：不再从请求头或连接信息取 IP/UA；下游传空则为空，未传则为空
            "ip": body.ip or "",
            "ua": body.ua or ""
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
        # 新规则：若幂等复用存在，则使用复用rid；否则用本次trace_id
        rid = udm.get("meta", {}).get("reuse_rid") or trace_id
        base = f"{callback_base}/cb?rid={rid}"
        try:
            if callback_template:
                from urllib.parse import urlparse
                parsed = urlparse(callback_template)
                if parsed.query:
                    return f"{base}&{parsed.query}"
        except Exception as e:
            logging.warning(f"Failed to parse callback template: {e}")
        return base

    helpers = {"cb_url": cb_url}  # 将回调模板通过token传递到回调环节

    # 渲染URL
    url = render_template(adapter["url"], adapter.get("macros", {}), ctx, secrets, helpers)
    logging.info(f"[to-upstream] click url: {url}")

    # 将上游最终URL保存（使用ORM以确保JSON/类型适配），并记录失败原因
    try:
        async with await get_session() as session:
            rid_to_use = (udm.get("meta", {}).get("reuse_rid") or trace_id)
            from sqlalchemy import select
            res = await session.execute(select(RequestLog).where(RequestLog.rid == rid_to_use))
            obj = res.scalar_one_or_none()
            if obj:
                obj.upstream_url = url
                await session.commit()
            else:
                logging.warning(f"RequestLog not found to set upstream_url, rid={rid_to_use}")
    except Exception as e:
        logging.error(f"Failed to update upstream_url: {e}")

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

    # 记录分发日志（已取消分发表，保留 request_log.upstream_url 即可）
    try:
        pass
    except Exception as e:
        logging.error(f"Error dispatching to upstream for trace_id {trace_id}: {e}")
    # 一次性 INSERT：准备所有字段后写入（若不存在）；若幂等复用，则仅确保 upstream_url 已写入
    try:
        async with await get_session() as session:
            from sqlalchemy import select
            res = await session.execute(select(RequestLog).where(RequestLog.rid == rid_to_use))
            obj = res.scalar_one_or_none()
            if obj is None:
                # 生成格式化时间（上海时区）
                from datetime import datetime, timezone, timedelta
                shanghai_tz = timezone(timedelta(hours=8))
                track_time_formatted = datetime.now(shanghai_tz).strftime("%Y-%m-%d %H:%M:%S")

                reqlog = RequestLog(
                    rid=rid_to_use,
                    ds_id=udm["meta"]["downstream_id"],
                    up_id=udm["meta"]["upstream_id"],
                    event_type=udm["event"]["type"],
                    ad_id=udm["ad"].get("ad_id"),
                    channel_id=udm["ad"].get("channel_id"),
                    click_id=udm["click"].get("id"),
                    ts=udm["time"]["ts"],
                    os=(udm.get("device") or {}).get("os"),
                    upload_params={
                        "query": dict(udm),
                        "callback_template": callback_template,
                    },
                    callback_params=None,
                    upstream_url=url,
                    downstream_url=None,
                    track_time=track_time_formatted,
                    is_callback_sent=0,
                    callback_time=None,
                    callback_event_type=None,
                )
                session.add(reqlog)
                await session.commit()
            else:
                # 已存在（幂等），上面已写入 upstream_url
                pass
    except Exception as e:
        logging.error(f"Failed to insert/update RequestLog: {e}")

    # 返回状态和响应（供调用方使用）
    return status, response



@router.get("/v1/track", response_model=APIResponse)
async def track_event(request: Request, response: Response,
                     ds_id: str,
                     event_type: str,
                     click_id: str = None,
                     ad_id: str = None,
                     channel_id: str = None,
                     ts: int = None,
                     ip: str = None,
                     ua: str = None,
                     # 设备信息
                     device_os: str = None,
                     device_model: str = None,
                     device_brand: str = None,
                     device_idfa: str = None,
                     device_caid: str = None,
                     device_oaid: str = None,
                     device_imei: str = None,
                     device_android_id: str = None,
                     device_os_version: str = None,
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
    支持的事件类型：click, imp
    """
    # 验证事件类型
    if event_type not in ["click", "imp"]:
        response.status_code = 500
        return APIResponse(success=False, code=500, message="Invalid event_type")

    # 生成链路追踪ID
    trace_id = str(uuid.uuid4())

    # 组装 device / user / ext
    device = {}
    if device_os: device["os"] = device_os
    if device_model: device["model"] = device_model
    if device_brand: device["brand"] = device_brand
    if device_idfa: device["idfa"] = device_idfa
    if device_caid: device["caid"] = device_caid
    if device_oaid: device["oaid"] = device_oaid
    if device_imei: device["imei"] = device_imei
    if device_android_id: device["android_id"] = device_android_id
    if device_os_version: device["os_version"] = device_os_version
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
        channel_id=channel_id,
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
        except Exception as e:
            logging.debug(f"Failed to decode callback URL, using raw value: {e}")
            callback_template = callback

    # 构造初始UDM用于路由
    udm_for_routing = _make_udm(body, request)
    
    # 幂等预查：如已存在相同 (ds_id,event_type,click_id) 记录，复用其 rid
    rid_existing = None
    try:
        async with await get_session() as session:
            from sqlalchemy import select
            res = await session.execute(
                select(RequestLog.rid)
                .where(
                    (RequestLog.ds_id == udm_for_routing["meta"]["downstream_id"]) &
                    (RequestLog.event_type == udm_for_routing["event"]["type"]) &
                    (RequestLog.click_id == udm_for_routing["click"]["id"])
                )
                .order_by(RequestLog.id.desc())
                .limit(1)
            )
            row = res.first()
            if row and row[0]:
                rid_existing = row[0]
    except Exception as e:
        logging.warning(f"Failed to check existing rid: {e}")

    rid_to_use = rid_existing or trace_id

    # 路由选择
    up_id, ds_out = choose_route(udm_for_routing, CONFIG)

    # 构造最终UDM，如果存在幂等复用，添加到meta中
    udm = _make_udm(body, request, up_id, body.ds_id)
    if rid_existing:
        udm["meta"]["reuse_rid"] = rid_existing

    # 直接一次写入：准备所有需要的字段，等待渲染出上游URL后，一次性保存
    # 注意：此处不再调用 _save_event_log，改为下方一次性 insert
    pass

    # 响应规则变更：
    #  - 未找到上游：400（not_found）
    #  - 找到上游但转发失败：按下方返回 500
    if not up_id:
        return APIResponse(success=False, code=500, message="链接已关闭")

    # 查找上游配置
    upstream_config = find_upstream_config(up_id, CONFIG)
    if not upstream_config:
        return APIResponse(success=False, code=500, message="链接已关闭")

    # 分发到上游，使用正确的rid（可能是复用的或新的）
    try:
        upstream_status, upstream_response = await _dispatch_to_upstream(
            rid_to_use, udm, upstream_config, event_type, callback_template
        )

        # 200 认为成功；其它按HTTP对齐
        if upstream_status == 200:
            return APIResponse(success=True, code=200, message="ok")
        else:
            # 非200均视为上游失败，统一返回500
            return APIResponse(success=False, code=500, message="network_error")

    except Exception as e:
        logging.error(f"Error dispatching to upstream: {e}")
        return APIResponse(success=False, code=500, message="server_error")
