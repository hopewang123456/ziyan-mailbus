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
    via_message_port: bool = False,
) -> dict[str, Any]:
    """Build contract, spawn via ProductionHarness, optionally wait.

    via_message_port=True（W7c）：先经 MessageTransportPort 写 inbox，再 Harness wait
    （file_bus 厚路径统一入口）。
    """
    if via_message_port and wait:
        from lib.application.transport_send import send_outbound

        mid = msg_id or (f"msg-{task_id}-{step_id}" if task_id and step_id else "")
        out = send_outbound(
            data_dir,
            agent_id=agent_id,
            msg_id=mid,
            intent=prompt,
            task_id=task_id,
            step_id=step_id,
            channel="file_bus",
            wait=True,
            allow_no_spawn=allow_no_spawn,
            wait_timeout_sec=timeout_seconds,
        )
        out["via"] = "message_transport_port"
        return out

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
            "status": outcome.status if hasattr(outcome, "status") else ("ok" if outcome.ok else "error"),
            "detail": getattr(outcome, "detail", "") or getattr(outcome, "error", "") or "",
        }
        out["ok"] = bool(outcome.ok)
    return out
