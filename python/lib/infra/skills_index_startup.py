"""Skills-index 启动时重建（写入 store/agents/json/skills-index.json）。

与 internal_llm/startup.py 同层：serve 启动编排放 infra，
核心构建逻辑在 lib.adapters.config.sync_layers（infra → adapters 不违反分层）。
"""

from __future__ import annotations


def rebuild_skills_index_on_start(data_dir: str) -> dict | None:
    """serve 启动时重跑 skills-index，返回 {changes, errors, skipped?}。"""
    try:
        from lib.adapters.config.sync_layers import write_skills_index_to_store
    except ImportError:
        return {"changes": 0, "errors": 0, "skipped": "sync_layers unavailable"}

    changes, errors = write_skills_index_to_store(data_dir=data_dir)
    return {"changes": len(changes), "errors": len(errors)}
