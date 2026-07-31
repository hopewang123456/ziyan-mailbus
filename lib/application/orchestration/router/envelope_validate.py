"""A2A Envelope 校验 — POST /api/tasks/create。"""
from __future__ import annotations

import re
from typing import List

_TASK_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,127}$")
_LEGACY_KEYS = frozenset({"title", "assignee", "steps", "pipeline"})


def is_legacy_create_body(body: dict) -> bool:
    if not isinstance(body, dict):
        return True
    return bool(_LEGACY_KEYS & set(body.keys())) and "intent" not in body


def validate_envelope(body: dict, *, data_dir: str = "") -> List[str]:
    errors: List[str] = []
    if not isinstance(body, dict):
        return ["body must be object"]

    for field in ("task_id", "intent", "initiator", "mode", "tier"):
        if field not in body:
            errors.append(f"missing {field}")

    tid = body.get("task_id") or ""
    if tid and not _TASK_ID_RE.match(tid):
        errors.append("invalid task_id format")

    mode = body.get("mode")
    if mode not in ("explicit", "auto"):
        errors.append("mode must be explicit or auto")

    if mode == "explicit":
        planned = body.get("planned_chain")
        if not isinstance(planned, list) or not planned:
            errors.append("explicit mode requires planned_chain")
        else:
            for i, step in enumerate(planned):
                if not isinstance(step, dict) or "role_type" not in step:
                    errors.append(f"planned_chain[{i}] missing role_type")

    tier = body.get("tier")
    if tier not in ("S", "M", "L", None):
        errors.append("tier must be S, M, or L")

    return errors
