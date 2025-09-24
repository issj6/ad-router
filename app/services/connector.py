import httpx
import asyncio
import json
import time
from typing import Dict, Any, Optional, Tuple
from ..utils.logger import info, warning, error

# 全局HTTP客户端
_client: Optional[httpx.AsyncClient] = None


async def get_client() -> httpx.AsyncClient:
    """获取全局HTTP客户端，使用连接池提高性能"""
    global _client
    if _client is None:
        # 关闭 httpx 默认日志，避免二次编码显示混淆
        import logging
        logging.getLogger("httpx").setLevel(logging.WARNING)

        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=8.0,  # 连接超时
                read=5.0,  # 读取超时
                write=5.0,  # 写入超时
                pool=10.0  # 连接池超时
            ),
            limits=httpx.Limits(
                max_keepalive_connections=700,  # 最大保持连接数
                max_connections=1000,  # 最大连接数
                keepalive_expiry=30.0  # 连接保持时间
            ),
            follow_redirects=False,
            verify=True  # 验证SSL证书
        )
    return _client


async def http_send(method: str, url: str, headers: Optional[Dict[str, str]] = None,
                    body: Any = None, timeout_ms: int = 5000) -> Tuple[int, Any]:
    """
    发送HTTP请求
    
    Args:
        method: HTTP方法（GET, POST等）
        url: 请求URL
        headers: 请求头
        body: 请求体（仅POST等方法使用）
        timeout_ms: 超时时间（毫秒）
    
    Returns:
        (status_code, response_data) 元组
    """
    client = await get_client()

    try:
        # 设置超时
        timeout = httpx.Timeout(timeout_ms / 1000.0)

        # 准备请求参数
        kwargs = {
            "url": url,
            "headers": headers or {},
            "timeout": timeout
        }

        # 根据方法发送请求
        method = method.upper()

        if method == "GET":
            response = await client.get(**kwargs)
        elif method == "POST":
            # 处理POST请求体
            if body is not None:
                content_type = (headers or {}).get("Content-Type", "")
                if content_type.startswith("application/json"):
                    kwargs["content"] = json.dumps(body).encode("utf-8")
                else:
                    kwargs["data"] = body
            response = await client.post(**kwargs)
        elif method == "PUT":
            if body is not None:
                content_type = (headers or {}).get("Content-Type", "")
                if content_type.startswith("application/json"):
                    kwargs["content"] = json.dumps(body).encode("utf-8")
                else:
                    kwargs["data"] = body
            response = await client.put(**kwargs)
        else:
            # 其他方法
            response = await client.request(method, **kwargs)

        # 解析响应
        try:
            response_data = response.json()
        except Exception:
            # 如果响应不是JSON格式，返回原始文本（这是正常情况，不需要记录错误）
            response_data = response.text

        return response.status_code, response_data

    except asyncio.CancelledError:
        # 传递取消，保证上层 wait_for 能在 submit 超时时及时返回
        raise
    except httpx.TimeoutException:
        warning(f"HTTP request timeout: {method} {url}")
        return 408, {"error": "timeout"}
    except httpx.ConnectError:
        warning(f"HTTP connection error: {method} {url}")
        return 503, {"error": "connection_failed"}
    except Exception as e:
        error(f"HTTP request error: {method} {url}, error: {e}")
        return 500, {"error": str(e)}


async def http_send_with_retry(method: str, url: str, headers: Optional[Dict[str, str]] = None,
                               body: Any = None, timeout_ms: int = 5000,
                               max_retries: int = 1, backoff_ms: int = 200) -> Tuple[int, Any]:
    """
    带重试的HTTP请求
    
    Args:
        method: HTTP方法
        url: 请求URL
        headers: 请求头
        body: 请求体
        timeout_ms: 超时时间（毫秒）
        max_retries: 最大重试次数
        backoff_ms: 重试间隔（毫秒）
    
    Returns:
        (status_code, response_data) 元组
    """
    # 语义修正：timeout_ms 视为“总超时预算”（包含所有尝试与退避等待）
    # 在预算内动态缩短每次尝试的超时，确保总耗时不超过 timeout_ms。
    last_status, last_response = 500, {"error": "no_attempt"}

    start_monotonic = time.monotonic()
    deadline = start_monotonic + (timeout_ms / 1000.0)

    attempt = 0
    while attempt <= max_retries:
        now = time.monotonic()
        remaining_sec = deadline - now
        if remaining_sec <= 0:
            # 预算已耗尽：若之前从未真正发起过请求，则返回超时；否则返回最后结果
            if last_status == 500 and last_response.get("error") == "no_attempt":
                return 408, {"error": "timeout"}
            return last_status, last_response

        # 为当前尝试分配超时（下限100ms，避免过短导致立刻超时）
        per_attempt_timeout_ms = max(100, int(remaining_sec * 1000))

        status, response = await http_send(
            method, url, headers, body, per_attempt_timeout_ms
        )

        last_status, last_response = status, response

        # 成功：2xx/3xx 不重试
        if 200 <= status < 400:
            break

        # 非超时错误：不重试
        if status != 408:
            break

        # 超时且还有重试机会，考虑退避但不超出预算
        attempt += 1
        if attempt > max_retries:
            break

        # 重新计算剩余预算，最多睡到 backoff 或预算用尽
        now = time.monotonic()
        remaining_sec = deadline - now
        if remaining_sec <= 0:
            break
        sleep_sec = min(backoff_ms / 1000.0, remaining_sec)
        if sleep_sec > 0:
            await asyncio.sleep(sleep_sec)
        info(f"Retrying HTTP request: {method} {url}, attempt {attempt + 1}")

    return last_status, last_response


async def cleanup_client():
    """清理HTTP客户端资源"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
