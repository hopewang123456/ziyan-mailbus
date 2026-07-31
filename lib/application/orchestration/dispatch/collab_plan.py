"""协作链扩展（显式 planned_chain 优先，无扩展时原样返回）。"""

from __future__ import annotations

from typing import List


def expand_planned_chain_for_collab(planned_chain: List[dict], body: dict) -> List[dict]:
    return list(planned_chain or [])
