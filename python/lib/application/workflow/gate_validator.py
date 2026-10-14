"""Workflow gate approve/deny 校验。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def validate_approve(body: dict, gate_def: Optional[dict] = None) -> List[str]:
    errs: List[str] = []
    if not (body.get("reviewer") or body.get("decision")):
        errs.append("missing reviewer")
    return errs


def validate_deny(body: dict, gate_def: Optional[dict] = None) -> List[str]:
    if not body.get("reason") and not body.get("comment"):
        return ["missing deny reason"]
    return []
