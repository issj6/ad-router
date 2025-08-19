import httpx
import asyncio
import json
import logging
from typing import Dict, Any, Optional, Tuple

# 全局HTTP客户端
_client: Optional[httpx.AsyncClient] = None


async def get_client() -> httpx.AsyncClient:
    """获取全局HTTP客户端，使用连接池提高性能"""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=2.0,  # 连接超时
                read=5.0,  # 读取超时
                write=5.0,  # 写入超时
                pool=10.0  # 连接池超时
            ),
            limits=httpx.Limits(
                max_keepalive_connections=100,  # 最大保持连接数
                max_connections=200,  # 最大连接数
                keepalive_expiry=30.0  # 连接保持时间
            ),
            follow_redirects=True,
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
            # 如果不是JSON，返回文本
            response_data = response.text

        return response.status_code, response_data

    except httpx.TimeoutException:
        logging.warning(f"HTTP request timeout: {method} {url}")
        return 408, {"error": "timeout"}
    except httpx.ConnectError:
        logging.warning(f"HTTP connection error: {method} {url}")
        return 503, {"error": "connection_failed"}
    except Exception as e:
        logging.error(f"HTTP request error: {method} {url}, error: {e}")
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
    # logging.info("********** 开始请求URL：" + url)
    last_status, last_response = 500, {"error": "no_attempt"}

    for attempt in range(max_retries + 1):
        status, response = await http_send(method, url, headers, body, timeout_ms)

        # 记录最后一次结果
        last_status, last_response = status, response

        # 成功或客户端错误（4xx）不重试
        if status < 500:
            break

        # 最后一次尝试，不再等待
        if attempt == max_retries:
            break

        # 等待后重试
        await asyncio.sleep(backoff_ms / 1000.0)
        logging.info(f"Retrying HTTP request: {method} {url}, attempt {attempt + 2}")

    return last_status, last_response


async def cleanup_client():
    """清理HTTP客户端资源"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
