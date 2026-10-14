"""Compat shim — 实际实现已下沉到 `lib.infra.pipeline_results`。

保留旧导入路径 `from lib.application.orchestration.pipeline.results import …`
不破坏；新代码请直接 import `lib.infra.pipeline_results`（避免 adapters→application
跨层违规）。
"""
from lib.infra.pipeline_results import (  # noqa: F401
    load_config,
    read_result_from_paths,
    result_paths_to_try,
    step_result_dir,
    step_result_path,
)

__all__ = [
    "load_config",
    "read_result_from_paths",
    "result_paths_to_try",
    "step_result_dir",
    "step_result_path",
]