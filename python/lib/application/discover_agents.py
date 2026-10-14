"""Discover / align use cases — depends on DiscoverySource port only."""
from __future__ import annotations

import os
from typing import Any, Sequence

from lib.interfaces.discovery import DiscoverySource
from lib.infra.utils import json_read, json_write

EXPECTED_LOCAL_MIN = 13

__all__ = [
    "EXPECTED_LOCAL_MIN",
    "align_store",
    "discover_agents",
    "save_report",
]


def discover_agents(sources: Sequence[DiscoverySource] | None = None) -> dict[str, Any]:
    if sources is None:
        from lib.composition import get_context

        sources = get_context().discovery_sources
    hits: list[dict[str, Any]] = []
    for src in sources:
        for d in src.scan():
            row: dict[str, Any] = {
                "source": d.source,
                "path": d.home_path or d.meta.get("container", ""),
                "framework": d.framework,
                "enabled": False,
            }
            row.update(dict(d.meta))
            hits.append(row)
    frameworks = sorted({h.get("framework") for h in hits if h.get("framework")})
    return {"hits": hits, "frameworks": frameworks, "count": len(hits)}


def align_store(data_dir: str, *, expect_min: int = EXPECTED_LOCAL_MIN) -> dict[str, Any]:
    from lib.composition import run_merge_store_config

    config_path = os.path.join(data_dir, "config.json")
    try:
        rc = run_merge_store_config(data_dir, quiet=True)
        if rc != 0 and not os.path.isfile(config_path):
            return {"ok": False, "error": "merge failed and no config", "agent_count": 0}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "agent_count": 0}

    cfg = json_read(config_path, {})
    agents = cfg.get("agents") or {}
    n = len(agents)
    discovery = discover_agents()
    fw_section = cfg.setdefault("frameworks", {})
    for fw in discovery.get("frameworks") or []:
        if fw not in fw_section:
            fw_section[fw] = {"enabled": False, "mount_mode": "container", "root_path": ""}
    for _aid, ac in agents.items():
        if isinstance(ac, dict) and "enabled" not in ac:
            ac["enabled"] = False
    json_write(config_path, cfg)

    ok = n >= expect_min
    return {
        "ok": ok,
        "agent_count": n,
        "expect_min": expect_min,
        "warning": None if ok else f"aligned agent_count={n} < expect_min={expect_min}",
        "discovery": discovery,
        "agent_ids": sorted(agents.keys()),
    }


def save_report(data_dir: str) -> dict[str, Any]:
    report = discover_agents()
    path = os.path.join(data_dir, "system", "discovery-report.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_write(path, report)
    return report
