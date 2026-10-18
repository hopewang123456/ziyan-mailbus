import urllib.request
try:
    body = urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=30).read().decode()
    print(body[:600])
except Exception as e:
    print("ERR", e)
