"""file_bus 异构交付 → canonical step-result（委托 delivery_normalizer）。"""
from __future__ import annotations

from typing import Optional

from ..delivery_normalizer import normalize_opencode_deliveries
from ..complexity_router import attach_mailbus_routing


def normalize_opencode_delivery(
    data_dir: str,
    task_id: str,
    step_id: str,
    sender: str,
    *,
    agents: Optional[dict] = None,
    config: Optional[dict] = None,
) -> dict | None:
    """单条 OpenCode 归一化；批量入口见 normalize_opencode_deliveries。"""
    stats = normalize_opencode_deliveries(data_dir, agents or {}, config=config)
    if stats.get("total", 0) <= 0:
        return None
    from .step_result_io import read_step_result_file

    return read_step_result_file(data_dir, task_id, step_id)


def normalize_with_routing(step_result: dict, routing: dict | None) -> dict:
    """step-result 附加 extensions.mailbus.routing（推送阶段 SquillaRouter 决策）。"""
    if not routing:
        return step_result
    return attach_mailbus_routing(step_result, routing)
