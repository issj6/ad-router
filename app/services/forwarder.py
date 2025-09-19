from typing import Any, Dict, Tuple
from ..config import CONFIG
from ..utils.logger import warning, error, perf_info
from ..services.router import get_adapter_config, find_upstream_config, choose_route
from ..mapping_dsl import render_template, eval_body_template
from ..services.connector import http_send_with_retry
from ..db import get_session
from ..models import RequestLog


async def dispatch_click_job(job: Dict[str, Any]) -> Tuple[int, Any]:
    """
    执行一次点击转发任务（用于去抖后台或同步路径）。

    必需字段：
    - trace_id: str
    - udm: Dict
    - upstream_id: str
    - event_type: str
    - callback_template: Optional[str]
    - route_params: Optional[Dict]
    """
    trace_id: str = job["trace_id"]
    udm: Dict[str, Any] = job["udm"]
    upstream_id: str = job["upstream_id"]
    event_type: str = job["event_type"]
    callback_template = job.get("callback_template")
    route_params = job.get("route_params") or {}

    # 二次路由校验：若当前配置已禁用或上游已变化，则丢弃任务，防止关闭后历史任务继续发送
    try:
        routing_udm = {
            "ad": (udm.get("ad") or {}),
            "meta": {
                "downstream_id": (udm.get("meta") or {}).get("downstream_id")
            },
        }
        current_up_id, _, current_enabled, _ = choose_route(routing_udm, CONFIG)
        # 规则：禁用直接丢弃；若当前命中上游与入队时不同，也丢弃，避免错发
        if (not current_enabled) or (current_up_id and current_up_id != upstream_id):
            warning(
                f"route_disabled_drop: rid={trace_id}, job_upstream={upstream_id}, "
                f"current_upstream={current_up_id}, enabled={current_enabled}"
            )
            return 200, {"msg": "route_disabled_drop"}
    except Exception as e:
        # 校验失败不阻断发送，但记录以便排障
        warning(f"route recheck failed, continue sending: {e}")

    upstream_config = find_upstream_config(upstream_id, CONFIG)
    if not upstream_config:
        return 500, {"msg": "upstream_not_found"}

    adapter = get_adapter_config(upstream_config, "outbound", event_type)
    if not adapter:
        warning(f"No outbound adapter for upstream {upstream_config['id']} event {event_type}")
        return 200, {"msg": "no_adapter"}

    ctx = {
        "udm": udm,
        "body": udm,
        "meta": {
            "ip": (udm.get("net") or {}).get("ip", ""),
            "ua": (udm.get("net") or {}).get("ua", ""),
        },
    }

    base_secrets = upstream_config.get("secrets", {}) or {}
    secrets = dict(base_secrets)
    try:
        if isinstance(route_params, dict):
            secrets.update({k: v for k, v in route_params.items()})
    except Exception:
        pass

    callback_base = CONFIG["settings"]["callback_base"].rstrip("/")

    def cb_url():
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

    helpers = {"cb_url": cb_url}

    url = render_template(adapter["url"], adapter.get("macros", {}), ctx, secrets, helpers)
    perf_info(f"[to-upstream] click url: {url}")

    method = adapter.get("method", "GET")
    headers = adapter.get("headers")

    body_template = adapter.get("body")
    body_data = None
    if body_template:
        body_data = eval_body_template(body_template, ctx, secrets, helpers)

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
        backoff_ms=backoff_ms,
    )

    track_status_value = 1 if status == 200 else 2

    try:
        async with await get_session() as session:
            from datetime import datetime, timezone, timedelta
            shanghai_tz = timezone(timedelta(hours=8))
            track_time_formatted = datetime.now(shanghai_tz).strftime("%Y-%m-%d %H:%M:%S")

            reqlog = RequestLog(
                rid=trace_id,
                ds_id=udm.get("meta", {}).get("downstream_id"),
                up_id=udm.get("meta", {}).get("upstream_id"),
                event_type=udm.get("event", {}).get("type"),
                ad_id=(udm.get("ad") or {}).get("ad_id"),
                channel_id=(udm.get("ad") or {}).get("channel_id"),
                ts=(udm.get("time") or {}).get("ts"),
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

    return status, response


