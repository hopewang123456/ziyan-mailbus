"""mailbus → team-memory.db + AgentMemory 双写桥接逻辑。"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .team_memory_store import (
    format_mailbus_content,
    is_available as sqlite_available,
    mailbus_message_key,
    store_memory,
)

SYNC_MARKER_FILE = "sync_to_memory.json"
PENDING_DIR = "agentmemory-pending"
BRIDGE_STATUS_FILE = "memory-bridge-last.json"

AGENTMEMORY_URL = os.environ.get("AGENTMEMORY_URL", "http://localhost:3111")


def _env_flag(name: str, default: bool = True) -> bool:
    val = os.environ.get(name, "1" if default else "0").strip().lower()
    return val not in ("0", "false", "no", "off")


def bridge_sqlite_enabled() -> bool:
    return _env_flag("MEMORY_BRIDGE_SQLITE", True)


def bridge_agentmemory_enabled() -> bool:
    return _env_flag("MEMORY_BRIDGE_AGENTMEMORY", True)


def normalize_inbox(inbox_data: Any, agent_name: str) -> list[dict]:
    if isinstance(inbox_data, list):
        return inbox_data
    if isinstance(inbox_data, dict):
        return inbox_data.get("messages", [])
    return []


def load_sync_marker(sync_file: Path) -> dict[str, set[str]]:
    """读取 sync marker；v1 flat array 视为 agentmemory 已同步。"""
    sqlite_ids: set[str] = set()
    am_ids: set[str] = set()
    if not sync_file.exists():
        return {"sqlite": sqlite_ids, "agentmemory": am_ids}
    try:
        raw = json.loads(sync_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"sqlite": sqlite_ids, "agentmemory": am_ids}
    if isinstance(raw, list):
        am_ids = set(raw)
    elif isinstance(raw, dict):
        if raw.get("v") == 2:
            sqlite_ids = set(raw.get("sqlite") or [])
            am_ids = set(raw.get("agentmemory") or [])
        else:
            am_ids = set(raw.get("agentmemory") or raw.get("synced") or [])
    return {"sqlite": sqlite_ids, "agentmemory": am_ids}


def save_sync_marker(sync_file: Path, sqlite_ids: set[str], am_ids: set[str]) -> None:
    payload = {
        "v": 2,
        "sqlite": sorted(sqlite_ids),
        "agentmemory": sorted(am_ids),
    }
    sync_file.parent.mkdir(parents=True, exist_ok=True)
    sync_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _should_skip_content(content: str) -> bool:
    if not content.strip():
        return True
    if "写入" in content and ".txt" in content:
        return True
    return False


def collect_pending_messages(data_dir: str) -> tuple[list[dict], dict[str, dict[str, set[str]]]]:
    """返回待同步消息及各 agent 的 sync marker 状态。"""
    inbox_dir = Path(data_dir) / "inbox"
    if not inbox_dir.is_dir():
        return [], {}

    messages: list[dict] = []
    markers: dict[str, dict[str, set[str]]] = {}

    for agent_dir in sorted(inbox_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_name = agent_dir.name
        inbox_file = agent_dir / "inbox.json"
        sync_file = agent_dir / SYNC_MARKER_FILE
        if not inbox_file.exists():
            continue

        with open(inbox_file, encoding="utf-8") as f:
            inbox_data = json.load(f)

        marker = load_sync_marker(sync_file)
        markers[agent_name] = marker

        for msg in normalize_inbox(inbox_data, agent_name):
            if not isinstance(msg, dict):
                continue
            msg_id = msg.get("id", "")
            status = msg.get("status", "")
            content = msg.get("content", "")
            if status != "acknowledged" or not msg_id:
                continue
            if _should_skip_content(content):
                continue

            needs_sqlite = bridge_sqlite_enabled() and msg_id not in marker["sqlite"]
            needs_am = bridge_agentmemory_enabled() and msg_id not in marker["agentmemory"]
            if not needs_sqlite and not needs_am:
                continue

            messages.append({
                "agent": agent_name,
                "msg_id": msg_id,
                "from": msg.get("from", "unknown"),
                "content": content,
                "type": msg.get("type", "notice"),
                "created_at": msg.get("created_at", ""),
                "needs_sqlite": needs_sqlite,
                "needs_agentmemory": needs_am,
            })

    return messages, markers


def get_agentmemory_health(url: str = "") -> dict:
    base = (url or AGENTMEMORY_URL).rstrip("/")
    endpoint = f"{base}/agentmemory/health"
    try:
        with urllib.request.urlopen(endpoint, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("error"):
                return data
            if data.get("status") == "healthy":
                return data
            return {"status": "unhealthy", **data}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body}"}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}
    except TimeoutError:
        return {"error": "timeout"}


def agentmemory_healthy(url: str = "") -> bool:
    health = get_agentmemory_health(url)
    return not health.get("error") and health.get("status") == "healthy"


def post_to_agentmemory(endpoint: str, payload: dict, url: str = "") -> dict:
    base = (url or AGENTMEMORY_URL).rstrip("/")
    req = urllib.request.Request(
        f"{base}{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except TimeoutError:
        return {"error": "timeout"}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body}"}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}


def write_memory_to_agentmemory(
    agent: str,
    msg_id: str,
    content: str,
    from_agent: str,
    msg_type: str,
    url: str = "",
) -> dict:
    tagged_content = f"[agent:{agent}] [from:{from_agent}] [msg_id:{msg_id}] {content[:2000]}"
    payload = {
        "content": tagged_content,
        "metadata": {
            "source": f"mailbus-{agent}",
            "from": from_agent,
            "to": agent,
            "msg_id": msg_id,
            "type": msg_type,
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }
    return post_to_agentmemory("/agentmemory/remember", payload, url=url)


def write_memory_to_sqlite(
    agent: str,
    msg_id: str,
    content: str,
    from_agent: str,
    msg_type: str,
) -> bool:
    key = mailbus_message_key(msg_id)
    body = format_mailbus_content(agent, from_agent, msg_type, content)
    return store_memory(key, body, category="mailbus", author=from_agent)


def process_pending_queue(data_dir: str, limit: int = 5, url: str = "") -> int:
    pending_dir = Path(data_dir) / PENDING_DIR
    if not pending_dir.is_dir() or not bridge_agentmemory_enabled():
        return 0
    if not agentmemory_healthy(url):
        return 0
    done = 0
    for fpath in sorted(pending_dir.glob("*.json"))[:limit]:
        data = json.loads(fpath.read_text(encoding="utf-8"))
        payload = data.get("payload") or data
        result = post_to_agentmemory("/agentmemory/remember", payload, url=url)
        if result.get("success") or result.get("memory"):
            fpath.unlink(missing_ok=True)
            done += 1
        elif result.get("error") == "timeout":
            break
    return done


def write_bridge_status(data_dir: str, stats: dict) -> None:
    system_dir = Path(data_dir) / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        **stats,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = system_dir / BRIDGE_STATUS_FILE
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_bridge(data_dir: str, limit: int = 20, url: str = "") -> dict:
    """执行一轮双写桥接，返回统计。"""
    stats = {
        "sqlite_ok": 0,
        "sqlite_fail": 0,
        "sqlite_skip": 0,
        "agentmemory_ok": 0,
        "agentmemory_fail": 0,
        "agentmemory_skip": 0,
        "pending_am": 0,
    }

    if bridge_agentmemory_enabled():
        stats["pending_am"] = process_pending_queue(data_dir, limit=5, url=url)

    messages, markers = collect_pending_messages(data_dir)
    if not messages:
        write_bridge_status(data_dir, stats)
        return stats

    am_ok = agentmemory_healthy(url) if bridge_agentmemory_enabled() else False
    sqlite_ok_env = bridge_sqlite_enabled() and sqlite_available()

    per_agent_updates: dict[str, dict[str, set[str]]] = {
        agent: {"sqlite": set(m["sqlite"]), "agentmemory": set(m["agentmemory"])}
        for agent, m in markers.items()
    }

    for msg in messages[: max(limit, 1)]:
        agent = msg["agent"]
        msg_id = msg["msg_id"]
        if agent not in per_agent_updates:
            per_agent_updates[agent] = {"sqlite": set(), "agentmemory": set()}

        if msg["needs_sqlite"]:
            if sqlite_ok_env:
                if write_memory_to_sqlite(
                    agent, msg_id, msg["content"], msg["from"], msg["type"]
                ):
                    per_agent_updates[agent]["sqlite"].add(msg_id)
                    stats["sqlite_ok"] += 1
                else:
                    stats["sqlite_fail"] += 1
            else:
                stats["sqlite_skip"] += 1

        if msg["needs_agentmemory"]:
            if am_ok:
                result = write_memory_to_agentmemory(
                    agent, msg_id, msg["content"], msg["from"], msg["type"], url=url
                )
                if result.get("success") or result.get("memory"):
                    per_agent_updates[agent]["agentmemory"].add(msg_id)
                    stats["agentmemory_ok"] += 1
                else:
                    stats["agentmemory_fail"] += 1
            else:
                stats["agentmemory_skip"] += 1

    for agent, sets in per_agent_updates.items():
        sync_file = Path(data_dir) / "inbox" / agent / SYNC_MARKER_FILE
        save_sync_marker(sync_file, sets["sqlite"], sets["agentmemory"])

    write_bridge_status(data_dir, stats)
    return stats
