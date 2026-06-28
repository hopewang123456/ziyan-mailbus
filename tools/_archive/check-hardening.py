#!/usr/bin/env python3
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
d = json.load(open("store/inbox/lingzhao/inbox.json"))
for m in d["messages"]:
    if "mailbus-hardening" in m.get("content", ""):
        print(m["id"], m.get("state"), m.get("status"), m.get("priority"))
