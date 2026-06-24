"""A2A Task Envelope 轻量校验（P1 · 不依赖 pip jsonschema）。"""

from __future__ import annotations

from typing import Any, Dict, List

from ..locale.role_labels import valid_role_types


def is_legacy_create_body(body: dict) -> bool:
    if not isinstance(body, dict):
        return True
    if body.get("chain") is not None and isinstance(body.get("chain"), list):
        if not body["chain"] or isinstance(body["chain"][0], str):
            return True
    if body.get("summary") and not body.get("intent"):
        return True
    if body.get("assignee") and not body.get("planned_chain"):
        return True
    if not body.get("protocol_version") and not body.get("mode"):
        return True
    return False


def validate_envelope(body: dict, *, data_dir: str = "") -> List[str]:
    errors: List[str] = []
    if not isinstance(body, dict):
        return ["body must be object"]

    for field in ("task_id", "intent", "initiator", "mode", "tier"):
        if not body.get(field):
            errors.append(f"missing_{field}")

    mode = body.get("mode")
    if mode not in ("explicit", "auto"):
        errors.append("invalid_mode")

    tier = body.get("tier")
    if tier not in ("S", "M", "L"):
        errors.append("invalid_tier")

    pv = body.get("protocol_version", "mailbus-a2a/1")
    if pv and not str(pv).startswith("mailbus-a2a/"):
        errors.append("unsupported_protocol_version")

    valid_rt = valid_role_types(data_dir or None)

    if mode == "explicit":
        pc = body.get("planned_chain")
        if not isinstance(pc, list) or not pc:
            errors.append("missing_planned_chain")
        else:
            for i, item in enumerate(pc):
                if not isinstance(item, dict):
                    errors.append(f"planned_chain[{i}]_not_object")
                    continue
                rt = item.get("role_type")
                if rt is None:
                    errors.append(f"planned_chain[{i}]_missing_role_type")
                elif int(rt) not in valid_rt:
                    errors.append(f"planned_chain[{i}]_invalid_role_type")

    constraints = body.get("constraints") or {}
    if isinstance(constraints, dict):
        for key in ("required_role_types", "forbidden_role_types", "optional_role_types"):
            for rt in constraints.get(key) or []:
                try:
                    if int(rt) not in valid_rt:
                        errors.append(f"constraints_{key}_invalid")
                except (TypeError, ValueError):
                    errors.append(f"constraints_{key}_invalid")

    acceptance = body.get("acceptance") or {}
    if acceptance:
        if not acceptance.get("criteria"):
            errors.append("acceptance_missing_criteria")
        if not acceptance.get("acceptor_role_type") and not acceptance.get("acceptor_agent"):
            errors.append("acceptance_missing_acceptor")

    return errors
