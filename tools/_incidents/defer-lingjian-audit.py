#!/usr/bin/env python3
"""Defer non-primary lingjian task so game-courier pipeline can use codex slot."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.models import Inbox, MsgStatus
from lib.utils import json_read, json_write, resolve_paths, _now_iso

DEFER_MSG = "audit-req-game-stellar-20260618"
AGENT = "lingjian"
PRIMARY = "game-courier-20260625"


def main() -> int:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store")
    paths = resolve_paths(data_dir)
    inbox_file = os.path.join(paths["inbox"], AGENT, "inbox.json")
    inbox = Inbox.from_dict(json_read(inbox_file, {}))
    n = 0
    for m in inbox.messages:
        mid = inbox.msg_field(m, "id", "")
        if mid != DEFER_MSG:
            continue
        content = inbox.msg_field(m, "content", "") or ""
        if PRIMARY in content:
            continue
        inbox.set_msg_status(
            mid,
            MsgStatus.ACKNOWLEDGED,
            state=MsgStatus.DONE,
            done_at=_now_iso(),
        )
        n += 1
        print(f"archived {AGENT} {mid} -> done (deferred for {PRIMARY})")
    if n:
        json_write(inbox_file, inbox.to_dict())
    else:
        print("nothing deferred")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
