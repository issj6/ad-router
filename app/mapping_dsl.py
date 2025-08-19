import urllib.parse
import hashlib
import hmac
import time
import re
from typing import Any, Dict, Union

def _get_path(ctx: Dict[str, Any], path: str) -> Any:
    """从上下文中获取路径值，支持点号分隔的嵌套路径"""
    if not path:
        return None
    
    cur = ctx
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur

def _apply_function(val: Any, fn: str) -> Any:
    """应用内置函数"""
    fn = fn.strip()
    
    if fn == "to_upper()":
        return str(val).upper() if val is not None else val
    elif fn == "to_lower()":
        return str(val).lower() if val is not None else val
    elif fn == "url_encode()":
        return urllib.parse.quote(str(val), safe="") if val is not None else val
    elif fn == "normalize_encode()":
        # 先反复解码直至稳定，再统一编码一次，避免二次编码
        if val is None:
            return val
        s = str(val)
        try:
            while True:
                u = urllib.parse.unquote(s)
                if u == s:
                    break
                s = u
        except Exception:
            pass
        return urllib.parse.quote(s, safe="")
    elif fn == "trim()":
        return str(val).strip() if val is not None else val
    elif fn.startswith("date_format("):
        # 简单支持 date_format('%s') → 返回时间戳字符串
        if val is not None:
            return str(val)
        return val
    elif fn == "hash_md5()":
        return hashlib.md5(str(val).encode()).hexdigest() if val is not None else val
    elif fn == "hash_sha256()":
        return hashlib.sha256(str(val).encode()).hexdigest() if val is not None else val
    
    return val

def eval_expr(expr: str, ctx: Dict[str, Any], secrets: Dict[str, str], helpers: Dict[str, Any]) -> Any:
    """
    评估DSL表达式
    支持的语法：
    - const:value - 常量值
    - secret_ref('key') - 获取密钥
    - hmac_sha256(secret, message) - HMAC签名
    - join(sep, [a,b,c]) - 连接字符串
    - cb_url() - 回调URL
    - path | fn() | fn2() - 管道操作
    - path.to.value - 路径访问
    """
    expr = expr.strip()
    
    # 常量值
    if expr.startswith("const:"):
        return expr[len("const:"):]
    
    # 密钥引用
    if expr.startswith("secret_ref("):
        # secret_ref('key') 或 secret_ref("key")
        match = re.match(r"secret_ref\(['\"]([^'\"]+)['\"]\)", expr)
        if match:
            key = match.group(1)
            return secrets.get(key, "")
        return ""
    
    # HMAC签名
    if expr.startswith("hmac_sha256("):
        # hmac_sha256(secret, message)
        inner = expr[len("hmac_sha256("):-1]
        try:
            # 简单分割，假设没有嵌套逗号
            parts = inner.split(",", 1)
            if len(parts) == 2:
                sec_expr = parts[0].strip()
                msg_expr = parts[1].strip()
                
                sec = eval_expr(sec_expr, ctx, secrets, helpers)
                msg = eval_expr(msg_expr, ctx, secrets, helpers)
                
                if sec is not None and msg is not None:
                    return hmac.new(str(sec).encode(), str(msg).encode(), hashlib.sha256).hexdigest()
        except Exception:
            pass
        return ""
    
    # 字符串连接
    if expr.startswith("join("):
        # join(sep, [a,b,c])
        inner = expr[len("join("):-1]
        try:
            # 找到第一个逗号分割分隔符和数组
            comma_idx = inner.find(",")
            if comma_idx > 0:
                sep_expr = inner[:comma_idx].strip()
                arr_expr = inner[comma_idx+1:].strip()
                
                # 处理分隔符（去掉引号）
                sep = sep_expr.strip("'\"")
                
                # 处理数组 [a,b,c]
                if arr_expr.startswith("[") and arr_expr.endswith("]"):
                    items_str = arr_expr[1:-1]
                    parts = []
                    
                    # 简单分割数组元素
                    for item in items_str.split(","):
                        item = item.strip()
                        if item:
                            v = eval_expr(item, ctx, secrets, helpers)
                            parts.append("" if v is None else str(v))
                    
                    return sep.join(parts)
        except Exception:
            pass
        return ""
    
    # coalesce函数：返回第一个非空值
    if expr.startswith("coalesce("):
        # coalesce('default_value') 或 coalesce(value, 'default')
        inner = expr[len("coalesce("):-1]
        try:
            # 简单处理，假设只有一个默认值参数
            default_value = inner.strip("'\"")
            return default_value
        except Exception:
            return ""

    # 回调URL助手
    if expr.startswith("cb_url("):
        return helpers.get("cb_url", lambda: "")()
    
    # 管道操作 "path | fn() | fn2()"
    if "|" in expr:
        parts = [x.strip() for x in expr.split("|")]
        val = eval_expr(parts[0], ctx, secrets, helpers)

        for fn in parts[1:]:
            # 处理coalesce函数
            if fn.startswith("coalesce("):
                if val is None or val == "":
                    inner = fn[len("coalesce("):-1]
                    val = inner.strip("'\"")
            else:
                val = _apply_function(val, fn)

        return val
    
    # 路径访问
    if "." in expr:
        return _get_path(ctx, expr)
    
    # 直接返回表达式（可能是简单值）
    return expr

def render_template(url_tmpl: str, macros: Dict[str, str], ctx: Dict[str, Any], secrets: Dict[str, str], helpers: Dict[str, Any]) -> str:
    """
    渲染URL模板，替换{{macro}}占位符
    """
    if not url_tmpl:
        return ""
    
    # 先计算每个宏的值
    values = {}
    for name, expr in (macros or {}).items():
        try:
            values[name] = eval_expr(expr, ctx, secrets, helpers)
        except Exception:
            values[name] = ""
    
    # 替换模板中的占位符
    result = url_tmpl
    for name, value in values.items():
        placeholder = "{{" + name + "}}"
        result = result.replace(placeholder, "" if value is None else str(value))
    
    return result

def eval_body_template(body_template: Any, ctx: Dict[str, Any], secrets: Dict[str, str], helpers: Dict[str, Any]) -> Any:
    """
    递归评估body模板中的表达式
    """
    if isinstance(body_template, dict):
        return {k: eval_body_template(v, ctx, secrets, helpers) for k, v in body_template.items()}
    elif isinstance(body_template, list):
        return [eval_body_template(item, ctx, secrets, helpers) for item in body_template]
    elif isinstance(body_template, str):
        return eval_expr(body_template, ctx, secrets, helpers)
    else:
        return body_template
