"""Push with harness contract — application facade (Wave1-C)."""
from __future__ import annotations

from typing import Any

from lib.harness.contract import HarnessContract, build_contract
from lib.harness.production import ProductionHarness


def push_with_contract(
    *,
    data_dir: str,
    agent_id: str,
    task_id: str = "",
    step_id: str = "",
    msg_id: str = "",
    prompt: str = "",
    domain_skill_ids: list[str] | None = None,
    timeout_seconds: int = 300,
    wait: bool = False,
    allow_no_spawn: bool = False,
) -> dict[str, Any]:
    """Build contract, spawn via ProductionHarness, optionally wait."""
    contract = build_contract(
        agent_id=agent_id,
        msg_id=msg_id,
        task_id=task_id,
        step_id=step_id,
        data_dir=data_dir,
        domain_skill_ids=domain_skill_ids or [],
        timeout_seconds=timeout_seconds,
    )
    harness = ProductionHarness()
    payload = {
        "data_dir": data_dir,
        "task_id": task_id,
        "step_id": step_id,
        "msg_id": msg_id or contract.msg_id,
        "prompt": prompt,
        "contract": contract,
        "domain_skill_ids": domain_skill_ids or [],
        "timeout_seconds": timeout_seconds,
        "allow_no_spawn": allow_no_spawn,
    }
    session = harness.spawn(agent_id, payload)
    out: dict[str, Any] = {
        "ok": True,
        "session_id": session.session_id,
        "msg_id": session.msg_id,
        "contract": contract.to_dict() if isinstance(contract, HarnessContract) else {},
    }
    if wait:
        outcome = harness.wait_completion(session, timeout=timeout_seconds)
        out["outcome"] = {
            "ok": outcome.ok,
            "status": outcome.status,
            "detail": getattr(outcome, "detail", "") or "",
        }
        out["ok"] = bool(outcome.ok)
    return out
