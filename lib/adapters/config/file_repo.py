"""File-backed ConfigRepository — config.json under file_lock RMW."""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping, Sequence

from lib.domain.types import AgentRef
from lib.utils import file_lock


class FileConfigRepository:
    def __init__(self, data_dir: str, *, lock_timeout: float = 10.0) -> None:
        self.data_dir = data_dir
        self.lock_timeout = float(lock_timeout)
        self._path = os.path.join(data_dir, "config.json")

    def get_raw(self) -> Mapping[str, Any]:
        return self._read_unlocked()

    def get_agent(self, agent_id: str) -> AgentRef | None:
        agents = self._agents_map(self._read_unlocked())
        entry = agents.get(agent_id)
        if not isinstance(entry, dict):
            return None
        return self._to_ref(agent_id, entry)

    def list_agents(self) -> Sequence[AgentRef]:
        agents = self._agents_map(self._read_unlocked())
        out: list[AgentRef] = []
        for aid, entry in agents.items():
            if isinstance(entry, dict):
                out.append(self._to_ref(str(aid), entry))
        return out

    def update(self, mutator: Callable[[dict[str, Any]], None]) -> None:
        """Read-modify-write config.json entirely under file_lock."""
        with file_lock(timeout=self.lock_timeout, path=self._path):
            data = self._read_unlocked()
            if not isinstance(data, dict):
                data = {}
            mutator(data)
            self._write_unlocked(data)

    def agent_config_mtime(self, agent_id: str) -> float | None:
        agents = self._agents_map(self._read_unlocked())
        if agent_id not in agents:
            return None
        try:
            return os.path.getmtime(self._path)
        except OSError:
            return None

    @staticmethod
    def _agents_map(raw: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
        agents = raw.get("agents") if isinstance(raw, Mapping) else None
        return agents if isinstance(agents, dict) else {}

    @staticmethod
    def _to_ref(agent_id: str, entry: Mapping[str, Any]) -> AgentRef:
        return AgentRef(
            agent_id=agent_id,
            framework=str(entry.get("type") or entry.get("framework") or ""),
            role_id=str(entry.get("role_id") or entry.get("role") or ""),
            mount=str(entry.get("mount_mode") or entry.get("mount") or ""),
            enabled=bool(entry.get("enabled", True)),
        )

    def _read_unlocked(self) -> dict[str, Any]:
        if not os.path.isfile(self._path):
            return {}
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)


def build_config_repo(data_dir: str, *, lock_timeout: float = 10.0) -> FileConfigRepository:
    return FileConfigRepository(data_dir, lock_timeout=lock_timeout)
