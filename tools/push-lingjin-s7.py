#!/usr/bin/env python3
import os, sys
MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)
from lib.commands import load_config
from lib.pusher import push_messages, resolve_cli_for_message
from lib.utils import json_read
from lib.models import Inbox

cfg = load_config(os.path.join(MAIL, "store", "config.json"))
data_dir = cfg["data_dir"]
ib = Inbox.from_dict(json_read(f"{data_dir}/inbox/lingjin/inbox.json", {}))
msg = next(m.to_dict() for m in ib.messages if "07865" in (m.id if hasattr(m, "id") else m.get("id", "")))
cli = resolve_cli_for_message(cfg["agents"]["lingjin"], cfg.get("agent_types", {}), msg, "lingjin")
print("pushing", msg["id"])
print("cli:", cli[:100])
push_messages(data_dir, "lingjin", [msg], cli_cmd=cli)
