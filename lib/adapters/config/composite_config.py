"""Composite ConfigRepository — MD agents overlay JSON file repo."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from lib.adapters.config.file_repo import FileConfigRepository
from lib.adapters.config.md_config import MdAgentsConfig, resolve_identities_root
from lib.domain.types import AgentRef


class CompositeConfigRepo:
    """Route agents section to Markdown identities, else JSON config.json."""

    def __init__(
        self,
        data_dir: str,
        *,
        lock_timeout: float = 10.0,
        identities_root: str | None = None,
        json_repo: FileConfigRepository | None = None,
        md: MdAgentsConfig | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.lock_timeout = float(lock_timeout)
        self._json = json_repo or FileConfigRepository(data_dir, lock_timeout=lock_timeout)
        raw = self._json.get_raw()
        root = identities_root or resolve_identities_root(config=raw if isinstance(raw, Mapping) else None)
        self._md = md or MdAgentsConfig(root)
        self.identities_root = root

    @property
    def _path(self) -> str:
        return self._json._path

    def get_raw(self) -> Mapping[str, Any]:
        data = dict(self._json.get_raw())
        md_agents = self._md.load_agents_map()
        if md_agents:
            agents = dict(data.get("agents") or {}) if isinstance(data.get("agents"), dict) else {}
            for aid, entry in md_agents.items():
                clean = {k: v for k, v in entry.items() if not str(k).startswith("_")}
                agents[aid] = {**(agents.get(aid) or {}), **clean}
            data["agents"] = agents
            data["identities_root"] = self.identities_root
        return data

    def get_agent(self, agent_id: str) -> AgentRef | None:
        md_ref = self._md.get_agent(agent_id)
        if md_ref is not None:
            return md_ref
        return self._json.get_agent(agent_id)

    def list_agents(self) -> Sequence[AgentRef]:
        by_id: dict[str, AgentRef] = {a.agent_id: a for a in self._json.list_agents()}
        for ref in self._md.list_agents():
            by_id[ref.agent_id] = ref
        return list(by_id.values())

    def update(self, mutator: Callable[[dict[str, Any]], None]) -> None:
        self._json.update(mutator)

    def agent_config_mtime(self, agent_id: str) -> float | None:
        md_m = self._md.agent_mtime(agent_id)
        json_m = self._json.agent_config_mtime(agent_id)
        if md_m is None:
            return json_m
        if json_m is None:
            return md_m
        return max(md_m, json_m)


def build_config_repo(
    data_dir: str,
    *,
    lock_timeout: float = 10.0,
    identities_root: str | None = None,
) -> CompositeConfigRepo:
    return CompositeConfigRepo(
        data_dir,
        lock_timeout=lock_timeout,
        identities_root=identities_root,
    )


def build_composite_config_repo(
    data_dir: str,
    *,
    lock_timeout: float = 10.0,
    identities_root: str | None = None,
) -> CompositeConfigRepo:
    return build_config_repo(
        data_dir,
        lock_timeout=lock_timeout,
        identities_root=identities_root,
    )
