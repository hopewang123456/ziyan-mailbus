"""Wave4: is_role_pipeline_task (current pipeline schema detector)."""
from __future__ import annotations

from lib.application.orchestration.pipeline.step import is_role_pipeline_task


def test_role_pipeline_detects_role_type():
    task = {"chain": [{"role_type": 1, "status": "running"}]}
    assert is_role_pipeline_task(task) is True


def test_role_pipeline_detects_planned_role_types():
    task = {"chain": [{"planned_role_types": [1, 8], "status": "running"}]}
    assert is_role_pipeline_task(task) is True


def test_non_role_pipeline_agent_only_chain():
    task = {"chain": [{"to_agent": "agent-i", "status": "running"}]}
    assert is_role_pipeline_task(task) is False
