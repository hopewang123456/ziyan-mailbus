"""Tier-0 spawn 规则 R0–R4（零 LLM）。

规则语义见 store/rules/intake-api-spec.md §5。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..constants import MAILBUS_ROOT
from ..tracker import TaskTracker
from ..utils import json_read
from .store import get, load_all
from .task_bridge import (
    SpawnError,
    spawn_analyze,
    spawn_by_kinds,
    spawn_commercial_design,
    spawn_video_publish,
)

DEFAULT_BRIDGE_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "auto_spawn_analyze": True,
    "auto_spawn_content": False,
    "auto_spawn_solution": False,
    "score_hint_min_for_ui": 75,
    "solution_tier_default": "M",
    "await_plan_approval_on_solution": True,
}

GATE_KIND = {
    "req_to_lingzhao": "solution",
    "content_start": "content",
}


@dataclass
class RuleMatch:
    rule: str
    action: str
    eligible: bool
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "action": self.action,
            "eligible": self.eligible,
            "reason": self.reason,
        }


def load_bridge_config(data_dir: str) -> dict:
    """SoT: store config mailbus_intake_bridge ← init-store 聚合 config/intake/bridge.json。"""
    bridge = dict(DEFAULT_BRIDGE_CONFIG)
    static_path = MAILBUS_ROOT / "config" / "intake" / "bridge.json"
    if static_path.is_file():
        bridge.update(json_read(str(static_path), {}))
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    bridge.update(cfg.get("mailbus_intake_bridge") or {})
    return bridge


def _gate_status(intake: dict, gate_id: str) -> str:
    for g in intake.get("commercial_gates") or []:
        if g.get("gate_id") == gate_id:
            return g.get("status") or "pending"
    return "pending"


def _analyze_task_id(intake: dict) -> Optional[str]:
    return (intake.get("pipeline_link") or {}).get("intake_task_id")


def _analyze_done(data_dir: str, intake: dict) -> bool:
    tid = _analyze_task_id(intake)
    if not tid:
        return False
    task = TaskTracker(data_dir).get(tid)
    if not task:
        return False
    status = (task.get("status") or "").lower()
    fsm = (task.get("fsm") or {}).get("state") or ""
    return status in ("done", "succeeded", "closed") or fsm in ("done", "succeeded", "closed")


def rule_r0_new_raw() -> RuleMatch:
    """R0：新 raw 入库 — 仅写 intake，不 spawn。"""
    return RuleMatch("R0", "none", True, "raw_ingest_only")


def rule_r1_spawn_analyze(intake: dict, config: dict) -> RuleMatch:
    """R1：decision=pending + 无 analyze task → 可 spawn Task A。"""
    if not config.get("auto_spawn_analyze", True):
        return RuleMatch("R1", "spawn_analyze", False, "auto_spawn_analyze_disabled")
    decision = (intake.get("decision") or "pending").lower()
    if decision not in ("pending", ""):
        return RuleMatch("R1", "spawn_analyze", False, f"decision={decision}")
    link = intake.get("pipeline_link") or {}
    if link.get("intake_task_id"):
        return RuleMatch("R1", "spawn_analyze", False, "analyze_task_exists")
    return RuleMatch("R1", "spawn_analyze", True, "missing_analyze_task")


def rule_r2_no_auto_solution(intake: dict, data_dir: str) -> RuleMatch:
    """R2：Task A done + pursue — 禁止自动 spawn 灵昭链。"""
    if (intake.get("decision") or "").lower() != "pursue":
        return RuleMatch("R2", "none", False, "not_pursue")
    if not _analyze_done(data_dir, intake):
        return RuleMatch("R2", "none", False, "analyze_not_done")
    return RuleMatch("R2", "block_auto_solution", True, "pursue_requires_manual_gate")


def rule_r3_spawn_solution(intake: dict, config: dict, *, manual: bool = False) -> RuleMatch:
    """R3：G1 req_to_lingzhao approved → spawn commercial_solution design。"""
    if _gate_status(intake, "req_to_lingzhao") != "approved":
        return RuleMatch("R3", "spawn_solution", False, "gate_not_approved")
    link = intake.get("pipeline_link") or {}
    if link.get("solution_task_id"):
        return RuleMatch("R3", "spawn_solution", False, "solution_task_exists")
    if not manual and not config.get("auto_spawn_solution", False):
        return RuleMatch("R3", "spawn_solution", False, "auto_spawn_solution_disabled")
    return RuleMatch("R3", "spawn_solution", True, "gate_approved")


def rule_r4_spawn_content(intake: dict, config: dict, *, manual: bool = False) -> RuleMatch:
    """R4：G4 content_start approved → spawn video_publish。"""
    if _gate_status(intake, "content_start") != "approved":
        return RuleMatch("R4", "spawn_content", False, "gate_not_approved")
    link = intake.get("pipeline_link") or {}
    if link.get("content_task_id"):
        return RuleMatch("R4", "spawn_content", False, "content_task_exists")
    if not manual and not config.get("auto_spawn_content", False):
        return RuleMatch("R4", "spawn_content", False, "auto_spawn_content_disabled")
    return RuleMatch("R4", "spawn_content", True, "gate_approved")


def evaluate(intake: dict, config: dict, *, data_dir: str = "") -> List[RuleMatch]:
    """评估 intake 当前适用的全部规则（诊断/bridge 用）。"""
    matches = [rule_r0_new_raw()]
    matches.append(rule_r1_spawn_analyze(intake, config))
    if data_dir:
        matches.append(rule_r2_no_auto_solution(intake, data_dir))
    matches.append(rule_r3_spawn_solution(intake, config))
    matches.append(rule_r4_spawn_content(intake, config))
    return matches


def spawn_on_gate_approved(
    data_dir: str,
    intake: dict,
    gate_id: str,
    *,
    brief: str = "",
) -> Optional[dict]:
    """闸门 approve 后 spawn（人工路径，不依赖 auto 标志）。"""
    kind = GATE_KIND.get(gate_id)
    if not kind:
        return None
    config = load_bridge_config(data_dir)
    if kind == "solution":
        match = rule_r3_spawn_solution(intake, config, manual=True)
        if not match.eligible:
            raise SpawnError("spawn_blocked", match.reason)
        return spawn_commercial_design(data_dir, intake, brief=brief)
    if kind == "content":
        match = rule_r4_spawn_content(intake, config, manual=True)
        if not match.eligible:
            raise SpawnError("spawn_blocked", match.reason)
        return spawn_video_publish(data_dir, intake)
    return None


def apply_bridge_action(data_dir: str, intake_id: str, match: RuleMatch, *, force: bool = False) -> dict:
    """执行 bridge 允许的自动 spawn（仅 R1 默认可自动；R3/R4 须 config 开启）。"""
    intake = get(data_dir, intake_id)
    if not intake:
        raise SpawnError("not_found", intake_id)
    if not match.eligible:
        return {"intake_id": intake_id, "rule": match.rule, "skipped": match.reason}

    if match.action == "spawn_analyze":
        return {"intake_id": intake_id, "rule": "R1", **spawn_analyze(data_dir, intake_id, force=force)}
    if match.action == "spawn_solution":
        out = spawn_by_kinds(data_dir, intake_id, ["solution"])
        return {"intake_id": intake_id, "rule": "R3", **out}
    if match.action == "spawn_content":
        out = spawn_by_kinds(data_dir, intake_id, ["content"])
        return {"intake_id": intake_id, "rule": "R4", **out}
    return {"intake_id": intake_id, "rule": match.rule, "action": match.action}


def bridge_reconcile(data_dir: str, *, force: bool = False) -> dict:
    """intake-bridge job：补漏 Task A；R3/R4 仅 config 开启时自动 spawn。"""
    config = load_bridge_config(data_dir)
    if not config.get("enabled", True):
        return {"status": "disabled", "results": []}

    results: List[dict] = []
    for intake in load_all(data_dir):
        iid = intake.get("intake_id", "")
        if not iid:
            continue
        r2 = rule_r2_no_auto_solution(intake, data_dir)
        if r2.eligible:
            results.append({"intake_id": iid, "rule": "R2", "skipped": r2.reason})

        r1 = rule_r1_spawn_analyze(intake, config)
        if r1.eligible:
            try:
                results.append(apply_bridge_action(data_dir, iid, r1, force=force))
            except SpawnError as exc:
                results.append({"intake_id": iid, "rule": "R1", "error": exc.code})

        for rule_fn, rule_id in (
            (lambda i: rule_r3_spawn_solution(i, config), "R3"),
            (lambda i: rule_r4_spawn_content(i, config), "R4"),
        ):
            m = rule_fn(intake)
            if m.eligible:
                try:
                    results.append(apply_bridge_action(data_dir, iid, m, force=force))
                except SpawnError as exc:
                    results.append({"intake_id": iid, "rule": rule_id, "error": exc.code})

    return {"status": "ok", "results": results}
