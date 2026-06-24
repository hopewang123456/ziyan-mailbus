"""显式协作模式 — dual_coding / peer_review 扩展 planned_chain。"""

from __future__ import annotations

from typing import Any, Dict, List

DEV_ROLE_TYPE = 8


def _first_dev_index(planned_chain: List[dict]) -> int:
    for i, item in enumerate(planned_chain):
        if int(item.get("role_type", -1)) == DEV_ROLE_TYPE:
            return i
    return -1


def expand_planned_chain_for_collab(
    planned_chain: List[dict],
    envelope: dict,
) -> List[dict]:
    """
    根据 envelope.constraints.dispatch 扩展 planned_chain：
    - dual_coding: 首个开发步拆为 lingyun + dali 并行 pin
    - peer_review: 在首个开发步后插入互审步（pin 另一开发）
    """
    from .tier_filter import dispatch_action_from_envelope

    action = dispatch_action_from_envelope(envelope)
    if not action.get("dual_coding") and not action.get("peer_review"):
        return planned_chain

    chain = [dict(x) for x in planned_chain]
    idx = _first_dev_index(chain)
    if idx < 0:
        return planned_chain

    if action.get("dual_coding"):
        dev = dict(chain[idx])
        dev["pin_agent"] = "lingyun"
        dev["collab_mode"] = "dual_coding"
        dev["reason"] = (dev.get("reason") or "") + " [dual:lingyun]"
        parallel = dict(chain[idx])
        parallel["pin_agent"] = "dali"
        parallel["collab_mode"] = "dual_coding"
        parallel["parallel_with"] = "dual"
        parallel["reason"] = (parallel.get("reason") or "") + " [dual:dali]"
        chain = chain[:idx] + [dev, parallel] + chain[idx + 1:]

    if action.get("peer_review"):
        idx2 = _first_dev_index(chain)
        if idx2 >= 0:
            review = {
                "role_type": DEV_ROLE_TYPE,
                "pin_agent": "dali" if chain[idx2].get("pin_agent") == "lingyun" else "lingyun",
                "collab_mode": "peer_review",
                "reason": "peer_review after dev step",
            }
            chain = chain[: idx2 + 1] + [review] + chain[idx2 + 1:]

    return chain
