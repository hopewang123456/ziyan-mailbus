"""HarnessContract — mailbus 调用时入参契约（JSON + 摘要）。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


SCHEMA = "mailbus-harness-contract-v1"
DEFAULT_SUMMARY_MAX_CHARS = 1200


@dataclass
class HarnessContract:
    """结构化契约；序列化进 msg-file / push payload。"""

    schema: str = SCHEMA
    agent_id: str = ""
    msg_id: str = ""
    task_id: str = ""
    step_id: str = ""
    # envelope (former L0)
    ack_path: str = ""
    msg_file_path: str = ""
    timeout_seconds: int = 300
    max_retries: int = 3
    forbid_phantom_done: bool = True
    # L1 delivery
    delivery_kind: str = "msg_results"  # D1
    delivery_path: str = ""
    framework: str = ""
    # L2
    archetype: str = ""
    role_bounds_summary: str = ""
    # L3 — only this work-order's skill ids
    domain_skill_ids: list[str] = field(default_factory=list)
    # mailbus rules/plans for this step
    rules_refs: list[str] = field(default_factory=list)
    rules_summary: str = ""
    # human-readable inline summary (token-budgeted)
    summary_text: str = ""
    dispatcher_role_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def build_summary(self, max_chars: int = DEFAULT_SUMMARY_MAX_CHARS) -> str:
        lines = [
            f"[mailbus contract] agent={self.agent_id} msg={self.msg_id}",
            f"ack → {self.ack_path or '(default inbox ack.json)'}",
            f"delivery → {self.delivery_path or f'msg-results/{{task}}/step-{{step}}.json'}",
            "禁止空泛「已完成」(forbid_phantom_done).",
        ]
        if self.role_bounds_summary:
            lines.append(f"role: {self.role_bounds_summary[:200]}")
        if self.domain_skill_ids:
            lines.append("skills: " + ", ".join(self.domain_skill_ids[:12]))
        if self.rules_summary:
            lines.append(f"rules: {self.rules_summary[:300]}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[: max_chars - 3] + "..."
        return text


def build_contract(
    *,
    agent_id: str,
    msg_id: str = "",
    task_id: str = "",
    step_id: str = "",
    data_dir: str = "",
    framework: str = "",
    archetype: str = "",
    role_bounds_summary: str = "",
    domain_skill_ids: list[str] | None = None,
    rules_refs: list[str] | None = None,
    rules_summary: str = "",
    dispatcher_role_id: str = "",
    timeout_seconds: int = 300,
    max_retries: int = 3,
    summary_max_chars: int = DEFAULT_SUMMARY_MAX_CHARS,
) -> HarnessContract:
    ack_path = ""
    msg_file = ""
    delivery = ""
    if data_dir and agent_id:
        ack_path = f"{data_dir.rstrip('/\\')}/inbox/{agent_id}/ack.json"
    if data_dir and msg_id:
        msg_file = f"{data_dir.rstrip('/\\')}/msg-files/{msg_id}.md"
    if data_dir and task_id and step_id:
        delivery = f"{data_dir.rstrip('/\\')}/msg-results/{task_id}/step-{step_id}.json"
    c = HarnessContract(
        agent_id=agent_id,
        msg_id=msg_id,
        task_id=task_id,
        step_id=step_id,
        ack_path=ack_path,
        msg_file_path=msg_file,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        delivery_kind="msg_results",
        delivery_path=delivery,
        framework=framework,
        archetype=archetype,
        role_bounds_summary=role_bounds_summary,
        domain_skill_ids=list(domain_skill_ids or []),
        rules_refs=list(rules_refs or []),
        rules_summary=rules_summary,
        dispatcher_role_id=dispatcher_role_id,
    )
    c.summary_text = c.build_summary(summary_max_chars)
    return c


def write_d1_step_result(
    data_dir: str,
    task_id: str,
    step_id: str,
    *,
    status: str,
    summary: str = "",
    agent_id: str = "",
    contract_id: str = "",
    artifacts: list[Any] | None = None,
    adapter_meta: dict | None = None,
) -> str:
    """D1 unified delivery path."""
    import os

    from ..utils import json_write

    rel = os.path.join("msg-results", task_id, f"step-{step_id}.json")
    path = os.path.join(data_dir, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = {
        "schema": "mailbus-step-result-v1",
        "task_id": task_id,
        "step_id": step_id,
        "status": status,
        "summary": summary,
        "agent_id": agent_id,
        "contract_id": contract_id,
        "artifacts": artifacts or [],
        "adapter_meta": adapter_meta or {},
    }
    json_write(path, body)
    return path
