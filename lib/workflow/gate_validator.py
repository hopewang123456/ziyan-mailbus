"""Gate approve/deny 请求校验。"""

from __future__ import annotations

from typing import List


def validate_approve(body: dict, gate_def: dict) -> List[str]:
    errors: List[str] = []
    attachments = body.get("attachments") or []
    min_att = int(gate_def.get("required_attachments_min") or 0)
    if len(attachments) < min_att:
        errors.append("missing_attachments")
    if gate_def.get("require_brief") and not (body.get("brief") or "").strip():
        errors.append("missing_brief")
    if gate_def.get("select_field") and not body.get("selected_copy_id"):
        errors.append("missing_select")
    return errors


def validate_deny(body: dict) -> List[str]:
    if not (body.get("reason") or "").strip():
        return ["missing_reason"]
    return []
