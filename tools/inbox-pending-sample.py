#!/usr/bin/env python3
import os, sys
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.models import Inbox
from lib.utils import json_read, resolve_paths

data_dir = "/mailbus/store"
agent = sys.argv[1] if len(sys.argv) > 1 else "lingzhao"
paths = resolve_paths(data_dir)
inbox = Inbox.from_dict(json_read(f"{paths['inbox']}/{agent}/inbox.json", {}))
pending = []
for m in inbox.messages:
    st = inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")
    if st != "pending":
        continue
    pending.append(m)
print(f"{agent} pending={len(pending)}")
types = Counter(inbox.msg_field(m, "type", "") for m in pending)
print("types", dict(types))
for m in pending[:8]:
    print("-", inbox.msg_field(m, "id", ""), inbox.msg_field(m, "type", ""),
          (inbox.msg_field(m, "content", "") or "")[:80].replace("\n", " "))
