"""Mount AgentMemory MCP when agent/framework is enabled; keep local memory always."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .agentmemory_config import agentmemory_url
from lib.infra.utils import json_read, json_write


def archive_agentmemory(data_dir: str, agent_id: str) -> str:
    """On disable: archive AM pending/local pointers under store/archive/am/."""
    src = os.path.join(data_dir, "agentmemory-pending", agent_id)
    dest_dir = os.path.join(data_dir, "archive", "agentmemory", agent_id)
    os.makedirs(dest_dir, exist_ok=True)
    marker = {
        "agent_id": agent_id,
        "archived": True,
        "pending_dir": src if os.path.isdir(src) else None,
    }
    path = os.path.join(dest_dir, "archive.json")
    json_write(path, marker)
    return path


def mcp_snippet_for_agent(agent_id: str, *, mail_root: str | None = None) -> dict[str, Any]:
    url = agentmemory_url(mail_root=mail_root)
    return {
        "mcpServers": {
            "agentmemory": {
                "url": url,
                "agentId": agent_id,
            }
        },
        "note": "Inject only when agent enabled on mailbus; local memory files remain.",
    }


def write_mcp_mount_hint(data_dir: str, agent_id: str) -> str:
    snip = mcp_snippet_for_agent(agent_id)
    path = os.path.join(data_dir, "system", "mcp-mounts", f"{agent_id}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_write(path, snip)
    return path


def clear_mcp_mount_hint(data_dir: str, agent_id: str) -> None:
    path = os.path.join(data_dir, "system", "mcp-mounts", f"{agent_id}.json")
    if os.path.isfile(path):
        os.remove(path)
