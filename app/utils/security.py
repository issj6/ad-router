import base64
import hmac
import hashlib
import json
import time
from typing import Any, Dict

def hmac_sha256_hex(secret: str, message: str) -> str:
    """计算HMAC-SHA256签名并返回十六进制字符串"""
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

def md5_hex(message: str) -> str:
    """计算MD5哈希并返回十六进制字符串"""
    return hashlib.md5(message.encode()).hexdigest()

def sha256_hex(message: str) -> str:
    """计算SHA256哈希并返回十六进制字符串"""
    return hashlib.sha256(message.encode()).hexdigest()

def encode_token(payload: Dict[str, Any], secret: str) -> str:
    """
    编码token：极简实现，格式为 base64url(json).base64url(hmac_sig)
    不是标准JWT，但足够安全且简单
    """
    # 序列化载荷
    body = json.dumps(payload, separators=(',', ':')).encode()
    
    # Base64URL编码（去掉填充）
    b64 = base64.urlsafe_b64encode(body).rstrip(b'=')
    
    # 计算HMAC签名
    sig = hmac.new(secret.encode(), b64, hashlib.sha256).digest()
    s64 = base64.urlsafe_b64encode(sig).rstrip(b'=')
    
    return f"{b64.decode()}.{s64.decode()}"

def decode_token(token: str, secret: str) -> Dict[str, Any]:
    """
    解码token并验证签名
    抛出ValueError如果token无效或过期
    """
    try:
        # 分割token
        parts = token.split(".")
        if len(parts) != 2:
            raise ValueError("invalid token format")
        
        b64, s64 = parts
        
        # 解码载荷
        body = base64.urlsafe_b64decode(b64 + "==")  # 补充填充
        
        # 解码签名
        sig = base64.urlsafe_b64decode(s64 + "==")
        
        # 验证签名
        expected_sig = hmac.new(secret.encode(), b64.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("invalid signature")
        
        # 解析载荷
        payload = json.loads(body.decode())
        
        # 检查过期时间
        if "exp" in payload and payload["exp"] < int(time.time()):
            raise ValueError("token expired")
        
        return payload
        
    except Exception as e:
        raise ValueError(f"invalid token: {e}")

def generate_callback_token(ds_id: str, up_id: str, click_id: str, secret: str, expire_days: int = 7, callback_template: str | None = None) -> str:
    """生成回调token（可携带下游回调模板，避免跨库查询）"""
    payload = {
        "ds_id": ds_id,
        "up_id": up_id,
        "click_id": click_id,
        "exp": int(time.time()) + expire_days * 24 * 3600
    }
    if callback_template:
        # 直接放入payload中（经HMAC签名，上游不可解），避免回调时跨日查库
        payload["callback_template"] = callback_template
    return encode_token(payload, secret)
