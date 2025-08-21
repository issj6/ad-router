import urllib.parse

val="Mozilla/5.0 (Linux; U; Android 14; zh-cn; PJU110 Build/TP1A.220905.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/115.0.5790.168 Mobile Safari/537.36 HeyTapBrowser/40.8.36.9"
print(urllib.parse.quote(str(val), safe=""))