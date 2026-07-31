"""Ack file helpers — ResultStorePort support (no private pusher deps)."""
from __future__ import annotations

from typing import Sequence

from lib.utils import json_read, resolve_paths


def list_unacked(data_dir: str, agent_id: str, msg_ids: Sequence[str]) -> list[str]:
    """Return subset of msg_ids that are not yet acked."""
    paths = resolve_paths(data_dir)
    ack_file = f"{paths['inbox']}/{agent_id}/ack.json"
    ack_data = json_read(ack_file, [])
    if isinstance(ack_data, dict):
        ack_data = [ack_data]
    acked_ids = {
        a.get("msg_id")
        for a in ack_data
        if isinstance(a, dict) and a.get("action") == "ack"
    }
    return [mid for mid in msg_ids if mid not in acked_ids]


def ack_message(data_dir: str, agent_id: str, msg_id: str) -> None:
    """Append an ack entry (idempotent-ish: callers may re-append)."""
    from lib.utils import json_write

    paths = resolve_paths(data_dir)
    ack_file = f"{paths['inbox']}/{agent_id}/ack.json"
    ack_data = json_read(ack_file, [])
    if isinstance(ack_data, dict):
        ack_data = [ack_data]
    if not isinstance(ack_data, list):
        ack_data = []
    if any(isinstance(a, dict) and a.get("msg_id") == msg_id and a.get("action") == "ack" for a in ack_data):
        return
    ack_data.append({"msg_id": msg_id, "action": "ack"})
    json_write(ack_file, ack_data)
