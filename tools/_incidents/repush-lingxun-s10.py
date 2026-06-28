#!/usr/bin/env python3
"""清理灵巡卡住的 Hermes CLI 并重推 game-courier s10。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.commands import load_config, run_scan_once
from lib.models import Inbox, MsgStatus
from lib.pusher import push_messages, resolve_cli_for_message
from lib.utils import json_write, json_read, rewrite_host_store_refs

DATA = ROOT / "store"
MSG_ID = "msg-20260625-51609"
AGENT = "lingxun"
CONTAINER = "docker-agents-hermes-1"


def kill_stale_hermes_chat(profile: str = "lingxun") -> int:
  import shutil
  wsl = shutil.which("wsl.exe") or shutil.which("wsl")
  if not wsl:
    return 0
  script = (
    f"docker exec {CONTAINER} bash -lc "
    f"\"ps aux | grep 'hermes chat.*--profile {profile}' | grep -v grep | awk '{{print $2}}' | xargs -r kill\""
  )
  r = subprocess.run([wsl, "bash", "-lc", script], capture_output=True, text=True)
  return r.returncode


def main() -> int:
  kill_stale_hermes_chat()

  cfg = load_config(str(DATA / "config.json"))
  inbox_path = DATA / "inbox" / AGENT / "inbox.json"
  inbox = Inbox.from_dict(json_read(str(inbox_path), {}))
  msg = None
  for m in inbox.messages:
    if inbox.msg_field(m, "id", "") == MSG_ID:
      msg = m if isinstance(m, dict) else m.to_dict()
      break
  if not msg:
    print("message not found", MSG_ID)
    return 1

  agent_cfg = cfg["agents"][AGENT]
  msg["content"] = rewrite_host_store_refs(str(DATA), msg.get("content", ""), agent_cfg)
  msg["state"] = MsgStatus.PENDING
  msg["status"] = MsgStatus.PENDING
  msg["pushed_count"] = 0
  msg["last_pushed_at"] = None
  inbox.set_msg_status(MSG_ID, MsgStatus.PENDING, state=MsgStatus.PENDING, pushed_count=0, last_pushed_at=None)
  json_write(str(inbox_path), inbox.to_dict())

  cli = resolve_cli_for_message(agent_cfg, cfg.get("agent_types", {}), msg, AGENT, data_dir=str(DATA))
  print("cli:", cli[:120], "...")
  failed = push_messages(
    data_dir=str(DATA),
    agent_name=AGENT,
    messages=[msg],
    cli_cmd=cli,
    auto_ack=False,
  )
  print("failed:", failed)
  if not failed:
    run_scan_once(str(DATA), cfg, quiet=True)
  return 0 if not failed else 2


if __name__ == "__main__":
  raise SystemExit(main())
