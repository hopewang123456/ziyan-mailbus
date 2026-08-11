"""application/ops — operational use-cases (Wave5+).

Keep this package ``__init__`` import-light: submodules (e.g. ``self_heal``)
are imported by ``scan`` and must not pull a circular graph via eager re-exports.
"""
from __future__ import annotations

__all__ = [
    "archive_inbox_backlog",
    "collect_watchdog_context",
    "fix_stuck_pipeline",
    "list_store_agents",
    "prune_agent_queues",
    "report_stuck_pipeline",
    "run_all_gates",
    "run_scout",
    "run_watchdog_pass",
]


def __getattr__(name: str):
    if name in ("collect_watchdog_context", "run_watchdog_pass"):
        from lib.application.ops.pipeline_watchdog import (
            collect_watchdog_context,
            run_watchdog_pass,
        )
        return {
            "collect_watchdog_context": collect_watchdog_context,
            "run_watchdog_pass": run_watchdog_pass,
        }[name]
    if name == "run_scout":
        from lib.application.ops.platform_scout import run_scout
        return run_scout
    if name in ("fix_stuck_pipeline", "report_stuck_pipeline"):
        from lib.application.ops.repair_pipeline import (
            fix_stuck_pipeline,
            report_stuck_pipeline,
        )
        return {
            "fix_stuck_pipeline": fix_stuck_pipeline,
            "report_stuck_pipeline": report_stuck_pipeline,
        }[name]
    if name in ("archive_inbox_backlog", "list_store_agents", "prune_agent_queues"):
        from lib.application.ops.store_cleanup import (
            archive_inbox_backlog,
            list_store_agents,
            prune_agent_queues,
        )
        return {
            "archive_inbox_backlog": archive_inbox_backlog,
            "list_store_agents": list_store_agents,
            "prune_agent_queues": prune_agent_queues,
        }[name]
    if name == "run_all_gates":
        from lib.application.ops.e2e_gates import run_all_gates
        return run_all_gates
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
