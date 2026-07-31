"""application/ops — operational use-cases (Wave5+)."""
from __future__ import annotations

from lib.application.ops.pipeline_watchdog import (
    collect_watchdog_context,
    run_watchdog_pass,
)
from lib.application.ops.platform_scout import run_scout
from lib.application.ops.repair_pipeline import fix_stuck_pipeline, report_stuck_pipeline
from lib.application.ops.store_cleanup import (
    archive_inbox_backlog,
    list_store_agents,
    prune_agent_queues,
)
from lib.application.ops.e2e_gates import run_all_gates

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
