#!/usr/bin/env python3
import json, sys
sys.path.insert(0, "/mailbus")
from lib.scanner import recover_inbox_stale_states
data = "/mailbus/store"
cfg = json.load(open(f"{data}/config.json"))
print("recover:", recover_inbox_stale_states(data, cfg.get("agents", {})))
for agent in ("lingxi",):
    for m in json.load(open(f"{data}/inbox/{agent}/inbox.json")).get("messages", []):
        if "162916" in m.get("content", ""):
            print(agent, m["id"], m.get("state"), m.get("status"))
