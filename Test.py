import urllib.parse
import uuid


def func(val):
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
    print(s)
    return urllib.parse.quote(s,safe="")

print(func("Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.104 Mobile Safari/537.36"))

print(uuid.uuid4())