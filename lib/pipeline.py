"""ziyan-mailbus 管道引擎（历史遗留，已归档）

2026-06-18 起由 lib/task_fsm.py + application/orchestration/pipeline 接管。
完整实现见 lib/_archived/pipeline_engine_legacy.py
"""

from ._archived.pipeline_engine_legacy import PipelineEngine, ROLE_TIMEOUT  # noqa: F401

__all__ = ["PipelineEngine", "ROLE_TIMEOUT"]
