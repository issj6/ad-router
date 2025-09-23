
from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import JSONResponse
from typing import Any, Dict
import asyncio
import uuid
import time
import datetime
import urllib.parse

from ..config import CONFIG
from ..db import get_session
from ..models import RequestLog
from ..schemas import TrackRequest, APIResponse
from ..services.router import choose_route, find_upstream_config, get_adapter_config, find_matching_rule
from ..services.connector import http_send_with_retry
from ..mapping_dsl import render_template, eval_body_template
from ..utils.security import generate_callback_token
from ..utils.logger import info, debug, warning, error, perf_info
from sqlalchemy.exc import IntegrityError
from ..services.debounce_redis import get_manager


router = APIRouter()


def _is_placeholder(value: str) -> bool:
    """检查字符串是否为未替换的占位符"""
    if not value:
        return False
    s = value.strip()
    return s.startswith("__") and s.endswith("__")


def _clean_query_placeholders(request: Request) -> Dict[str, Any]:
    """对请求的 query 参数做占位符清洗：形如 __xxx__ 的字符串置为空串"""
    cleaned: Dict[str, Any] = {}
    for key, val in request.query_params.items():
        if isinstance(val, str) and _is_placeholder(val):
            cleaned[key] = ""
        else:
            cleaned[key] = val
    return cleaned


def _make_udm(body: TrackRequest, request: Request, up_id: str = None, ds_id: str = None) -> Dict[str, Any]:
    """构造统一数据模型(UDM)"""
    # 默认使用13位毫秒时间戳
    now = int(time.time() * 1000)

    return {
        "event": {
            "type": body.event_type
        },
        "click": {
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


def _build_device_key(udm: Dict[str, Any]) -> str:
    """根据优先级计算设备唯一键，兜底使用 ip+ua+os。"""
    device = udm.get("device") or {}
    net = udm.get("net") or {}
    for k in ("idfa", "oaid", "imei", "android_id", "caid"):
        v = device.get(k)
        if v:
            return f"{k}:{str(v).strip().lower()}"
    ip = (net.get("ip") or "").strip().lower()
    ua = (net.get("ua") or "").strip().lower()
    os_name = (device.get("os") or "").strip().lower()
    if ip or ua or os_name:
        return f"ipuaos:{ip}|{ua}|{os_name}"
    return "unknown"

async def _dispatch_to_upstream(trace_id: str, udm: Dict[str, Any], upstream_config: Dict[str, Any],
                               event_type: str, callback_template: str | None = None,
                               route_params: Dict[str, Any] | None = None) -> tuple[int, Any]:
    """分发到上游"""
    # 获取适配器配置
    adapter = get_adapter_config(upstream_config, "outbound", event_type)
    if not adapter:
        warning(f"No outbound adapter for upstream {upstream_config['id']} event {event_type}")
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

    # 合并 secrets：路由级 custom_params 覆盖上游 secrets
    base_secrets = upstream_config.get("secrets", {}) or {}
    secrets = dict(base_secrets)
    if route_params and isinstance(route_params, dict):
        try:
            secrets.update({k: v for k, v in route_params.items()})
        except Exception:
            pass

    # 准备回调URL助手
    app_secret = CONFIG["settings"]["app_secret"]
    callback_base = CONFIG["settings"]["callback_base"].rstrip("/")

    def cb_url():
        # 直接使用当前 trace_id 作为 rid
        base = f"{callback_base}/cb?rid={trace_id}"
        try:
            if callback_template:
                from urllib.parse import urlparse
                parsed = urlparse(callback_template)
                if parsed.query:
                    return f"{base}&{parsed.query}"
        except Exception as e:
            warning(f"Failed to parse callback template: {e}")
        return base

    helpers = {"cb_url": cb_url}  # 将回调模板通过token传递到回调环节

    # 渲染URL
    url = render_template(adapter["url"], adapter.get("macros", {}), ctx, secrets, helpers)
    perf_info(f"[to-upstream] click url: {url}")



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

    # 根据上游响应状态设置发送状态（与接口返回语义保持一致：仅200视为成功）
    track_status_value = 1 if status == 200 else 2

    # 记录分发日志（已取消分发表，保留 request_log.upstream_url 即可）
    try:
        pass
    except Exception as e:
        error(f"Error dispatching to upstream for trace_id {trace_id}: {e}")
    # 一次性 INSERT：准备所有字段后写入，包含 upstream_url
    try:
        async with await get_session() as session:
            # 生成格式化时间（上海时区）
            from datetime import datetime, timezone, timedelta
            shanghai_tz = timezone(timedelta(hours=8))
            track_time_formatted = datetime.now(shanghai_tz).strftime("%Y-%m-%d %H:%M:%S")

            reqlog = RequestLog(
                rid=trace_id,  # 直接使用新生成的 trace_id，不再有复用逻辑
                ds_id=udm["meta"]["downstream_id"],
                up_id=udm["meta"]["upstream_id"],
                event_type=udm["event"]["type"],
                ad_id=udm["ad"].get("ad_id"),
                channel_id=udm["ad"].get("channel_id"),

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
                track_status=track_status_value,
                is_callback_sent=0,
                callback_time=None,
                callback_event_type=None,
            )
            session.add(reqlog)
            await session.commit()
    except Exception as e:
        error(f"Failed to insert RequestLog: {e}")

    # 返回状态和响应（供调用方使用）
    return status, response



@router.get("/v1/track", response_model=APIResponse)
async def track_event(request: Request, response: Response,
                     ds_id: str,
                     event_type: str,
                     ad_id: str = None,
                     channel_id: str = None,
                     ts: str = None,  # 改为字符串，避免422错误
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
    # 入口统一清洗：将 query 中形如 __xxx__ 的值置为空串
    cleaned_query = _clean_query_placeholders(request)
    
    # 检查必需参数是否为占位符（ds_id, event_type 必须有效）
    ds_id_val = cleaned_query.get("ds_id", ds_id)
    if not ds_id_val:  # 清洗后为空说明原来是占位符
        response.status_code = 400
        return APIResponse(success=False, code=400, message="ds_id包含未替换的占位符，请检查调用方配置")
    
    event_type_val = cleaned_query.get("event_type", event_type)
    if not event_type_val:  # 清洗后为空说明原来是占位符
        response.status_code = 400
        return APIResponse(success=False, code=400, message="event_type包含未替换的占位符，请检查调用方配置")
    
    # 验证事件类型
    if event_type_val not in ["click", "imp"]:
        response.status_code = 400
        return APIResponse(success=False, code=400, message="event_type必须为click或imp")
    
    # 处理时间戳参数
    ts_int = None
    ts_val = cleaned_query.get("ts", ts)
    if ts_val:
        try:
            ts_int = int(ts_val)
        except ValueError:
            response.status_code = 400
            return APIResponse(success=False, code=400, message="时间戳格式错误，必须为数字")

    # 生成链路追踪ID
    trace_id = str(uuid.uuid4())

    # 组装 device / user / ext
    device = {}
    if cleaned_query.get("device_os"): device["os"] = cleaned_query.get("device_os")
    if cleaned_query.get("device_model"): device["model"] = cleaned_query.get("device_model")
    if cleaned_query.get("device_brand"): device["brand"] = cleaned_query.get("device_brand")
    if cleaned_query.get("device_idfa"): device["idfa"] = cleaned_query.get("device_idfa")
    if cleaned_query.get("device_caid"): device["caid"] = cleaned_query.get("device_caid")
    if cleaned_query.get("device_oaid"): device["oaid"] = cleaned_query.get("device_oaid")
    if cleaned_query.get("device_imei"): device["imei"] = cleaned_query.get("device_imei")
    if cleaned_query.get("device_android_id"): device["android_id"] = cleaned_query.get("device_android_id")
    if cleaned_query.get("device_os_version"): device["os_version"] = cleaned_query.get("device_os_version")
    if cleaned_query.get("device_mac"): device["mac"] = cleaned_query.get("device_mac")

    user = {}
    if cleaned_query.get("user_phone_md5"): user["phone_md5"] = cleaned_query.get("user_phone_md5")
    if cleaned_query.get("user_email_sha256"): user["email_sha256"] = cleaned_query.get("user_email_sha256")

    ext = {}
    if cleaned_query.get("ext_custom_id"): ext["custom_id"] = cleaned_query.get("ext_custom_id")

    # 构造与原POST一致的请求体模型
    body = TrackRequest(
        ds_id=ds_id_val,
        event_type=event_type_val,
        ad_id=cleaned_query.get("ad_id", ad_id),
        channel_id=cleaned_query.get("channel_id", channel_id),
        ts=ts_int,  # 使用转换后的整数时间戳
        ip=cleaned_query.get("ip", ip),
        ua=cleaned_query.get("ua", ua),
        device=device or None,
        user=user or None,
        ext=ext or None
    )

    # 解析并保存下游回调模板（URL编码→解码后保存）
    callback_template: str | None = None
    callback_val = cleaned_query.get("callback", callback)
    if callback_val:
        try:
            callback_template = urllib.parse.unquote(callback_val)
        except Exception as e:
            debug(f"Failed to decode callback URL, using raw value: {e}")
            callback_template = callback_val

    # 构造初始UDM用于路由
    udm_for_routing = _make_udm(body, request)
    
    # 新的幂等性设计：每次生成新的 rid，不再复用
    rid_to_use = trace_id

    # 路由选择
    up_id, ds_out, enabled, throttle = choose_route(udm_for_routing, CONFIG)
    
    # 检查路由是否启用
    if not enabled:
        response.status_code = 400
        return APIResponse(success=False, code=400, message="链接已关闭")

    # 构造最终UDM
    udm = _make_udm(body, request, up_id, body.ds_id)

    # 直接一次写入：准备所有需要的字段，等待渲染出上游URL后，一次性保存
    # 注意：此处不再调用 _save_event_log，改为下方一次性 insert
    pass

    # 响应规则变更：
    #  - 路由被禁用：400（链接已关闭）
    #  - 未找到上游：400（not_found）
    #  - 找到上游但转发失败：按下方返回 500
    if not up_id:
        response.status_code = 400
        return APIResponse(success=False, code=400, message="链接已关闭")

    # 查找上游配置
    upstream_config = find_upstream_config(up_id, CONFIG)
    if not upstream_config:
        return APIResponse(success=False, code=500, message="链接已关闭")

    # 提取路由级 custom_params（如存在）
    route_params: Dict[str, Any] = {}
    try:
        matched_rule = find_matching_rule(udm_for_routing, CONFIG)
        if isinstance(matched_rule, dict):
            rp = matched_rule.get("custom_params")
            if isinstance(rp, dict):
                route_params = rp
    except Exception as e:
        debug(f"failed to load route custom_params: {e}")

    # 读取去抖开关：全局优先级最高。全局关闭则强制禁用；全局开启时，路由可单独关闭。
    debounce_enabled: bool = False
    try:
        global_debounce = bool(CONFIG.get("settings", {}).get("debounce", {}).get("enabled", False))
        route_debounce = None
        if isinstance(matched_rule, dict):
            route_debounce = matched_rule.get("debounce")
        if not global_debounce:
            debounce_enabled = False
        else:
            if isinstance(route_debounce, bool):
                debounce_enabled = (route_debounce is True)
            else:
                debounce_enabled = True
    except Exception:
        debounce_enabled = False

    if debounce_enabled:
        # 仅转发最后一条：提交到去抖管理器，由后台定时发送
        try:
            max_wait_ms = int(CONFIG.get("settings", {}).get("debounce", {}).get("max_wait_ms", 20000))
        except Exception:
            max_wait_ms = 20000
        # 使用服务端时间保证排序单调，避免客户端乱序覆盖
        _client_ts = int(udm.get("time", {}).get("ts") or 0)
        _now_ts = int(time.time() * 1000)
        order_ts_ms = _client_ts if _client_ts > _now_ts else _now_ts
        device_key = _build_device_key(udm)
        debounce_key = f"{up_id}:{udm.get('ad', {}).get('ad_id', '')}:{device_key}"

        # 构建可序列化任务，便于 Redis 去抖
        job = {
            "trace_id": rid_to_use,
            "udm": udm,
            "upstream_id": up_id,
            "event_type": event_type,
            "callback_template": callback_template,
            "route_params": route_params,
        }

        try:
            manager = get_manager()
            # 守护：若管理器未运行则自动拉起，避免非标准启动导致后台未工作
            if not getattr(manager, "_running", False):
                try:
                    await manager.start()
                except Exception as _e:
                    warning(f"Debounce manager auto-start failed: {_e}")
            # Redis 版：走 submit_job；内存版：走 submit
            # 前台提交超时保护：超时快速返回并在后台补提/直发
            try:
                submit_timeout_ms = int(CONFIG.get("settings", {}).get("debounce", {}).get("submit_timeout_ms", 50))
            except Exception:
                submit_timeout_ms = 50

            if hasattr(manager, "submit_job"):
                try:
                    await asyncio.wait_for(
                        manager.submit_job(
                            key=debounce_key,
                            order_ts_ms=order_ts_ms,
                            max_wait_ms=max_wait_ms,
                            job=job,
                        ),
                        timeout=submit_timeout_ms / 1000.0,
                    )
                except asyncio.TimeoutError:
                    warning("Debounce submit timed out, schedule background submit")
                    try:
                        asyncio.create_task(
                            manager.submit_job(
                                key=debounce_key,
                                order_ts_ms=order_ts_ms,
                                max_wait_ms=max_wait_ms,
                                job=job,
                            )
                        )
                    except Exception as _bg_e:
                        warning(f"schedule submit_job failed: {_bg_e}")
            else:
                async def _send_factory():
                    try:
                        from ..services.forwarder import dispatch_click_job
                        await dispatch_click_job(job)
                    except Exception as e:
                        error(f"Debounce send failed: {e}")

                try:
                    await asyncio.wait_for(
                        manager.submit(
                            key=debounce_key,
                            order_ts_ms=order_ts_ms,
                            max_wait_ms=max_wait_ms,
                            send_factory=_send_factory,
                        ),
                        timeout=submit_timeout_ms / 1000.0,
                    )
                except asyncio.TimeoutError:
                    warning("Debounce submit (memory) timed out, schedule background submit")
                    try:
                        asyncio.create_task(
                            manager.submit(
                                key=debounce_key,
                                order_ts_ms=order_ts_ms,
                                max_wait_ms=max_wait_ms,
                                send_factory=_send_factory,
                            )
                        )
                    except Exception as _bg_e:
                        warning(f"schedule memory submit failed: {_bg_e}")
        except Exception as e:
            warning(f"Debounce submit failed, fallback to direct send: {e}")
            try:
                from ..services.forwarder import dispatch_click_job
                upstream_status, upstream_response = await dispatch_click_job(job)
                if upstream_status != 200:
                    return APIResponse(success=False, code=500, message="network_error")
            except Exception as ex:
                error(f"Fallback direct send failed: {ex}")
                return APIResponse(success=False, code=500, message="server_error")

        # 去抖模式：接受请求并返回成功，实际发送在后台完成
        return APIResponse(success=True, code=200, message="ok")

    # 非去抖：同步发送
    try:
        upstream_status, upstream_response = await _dispatch_to_upstream(
            rid_to_use, udm, upstream_config, event_type, callback_template, route_params
        )

        if upstream_status == 200:
            return APIResponse(success=True, code=200, message="ok")
        else:
            return APIResponse(success=False, code=500, message="network_error")

    except Exception as e:
        error(f"Error dispatching to upstream: {e}")
        return APIResponse(success=False, code=500, message="server_error")
