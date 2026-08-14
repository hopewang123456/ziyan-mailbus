"""Role transfer saga — migrate agent registry entry across frameworks."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from lib.infra.utils import json_read, json_write


def transfer_role(
    data_dir: str,
    *,
    role_id: str,
    from_framework: str,
    to_framework: str,
    new_role_id: str | None = None,
) -> dict[str, Any]:
    """Move agent registry entry; relocate inbox unread; archive AM; drop source.

    Requires ``from_framework`` to match the source agent's type/framework.
    """
    from lib.composition import get_integrations

    cfg_path = os.path.join(data_dir, "config.json")
    cfg = json_read(cfg_path, {})
    agents = cfg.get("agents") or {}
    if role_id not in agents:
        return {"ok": False, "error": f"unknown role {role_id}"}
    src = dict(agents[role_id])
    if (src.get("type") or src.get("framework")) != from_framework:
        return {"ok": False, "error": "from_framework mismatch"}

    dest_id = new_role_id or role_id
    if dest_id in agents and dest_id != role_id:
        return {"ok": False, "error": f"dest id exists: {dest_id}"}

    dest = dict(src)
    dest["type"] = to_framework
    dest["framework"] = to_framework
    dest["id"] = dest_id
    dest["enabled"] = False  # require explicit enable after transfer

    inbox_src = Path(data_dir) / "inbox" / role_id
    inbox_dst = Path(data_dir) / "inbox" / dest_id
    if inbox_src.exists() and role_id != dest_id:
        if inbox_dst.exists():
            s = json_read(str(inbox_src / "inbox.json"), {"messages": []})
            d = json_read(str(inbox_dst / "inbox.json"), {"messages": []})
            msgs = list(d.get("messages") or []) + list(s.get("messages") or [])
            inbox_dst.mkdir(parents=True, exist_ok=True)
            json_write(str(inbox_dst / "inbox.json"), {"has_unread": bool(msgs), "messages": msgs})
            shutil.rmtree(inbox_src, ignore_errors=True)
        else:
            inbox_src.rename(inbox_dst)

    get_integrations().archive_agentmemory(data_dir, role_id)

    if dest_id != role_id:
        del agents[role_id]
    agents[dest_id] = dest
    json_write(cfg_path, cfg)
    return {"ok": True, "from": role_id, "to": dest_id, "framework": to_framework}
