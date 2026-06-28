import json
import urllib.request
import urllib.error

req = urllib.request.Request(
    "http://127.0.0.1:9814/api/launch?_t=1",
    data=json.dumps({"agent": "lingxiao", "mode": "desktop"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        print(r.status, r.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode("utf-8"))
