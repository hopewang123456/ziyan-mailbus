#!/usr/bin/env python3
import sys
sys.path.insert(0, "/mailbus")
from lib.scanner import recover_inbox_stale_states, update_message_status
from lib.models import MsgStatus
from lib.utils import json_read

dd = "/mailbus/store"
tid = "game-stellar-v3-20260617"
cfg = json_read(f"{dd}/config.json", {})
print("recover:", recover_inbox_stale_states(dd, cfg.get("agents", {})))
update_message_status(dd, "xiaoqi", "msg-20260617-01245", MsgStatus.PENDING)
print("xiaoqi msg-20260617-01245 -> pending")
