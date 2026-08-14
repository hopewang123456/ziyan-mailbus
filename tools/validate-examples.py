#!/usr/bin/env python3
"""校验 store/examples/*.json 结构与 registry / role-types 引用。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "store" / "examples"
REGISTRY = ROOT / "store" / "workflows" / "registry.json"
ROLE_TYPES = ROOT / "store" / "roles" / "json" / "role-types.json"

INTAKE_ID = re.compile(r"^intake-[0-9]{8}-[a-z0-9]{6}$")
TASK_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,127}$")
GATE_IDS = {
    "contact_done",
    "req_to_solution",
    "customer_design_ok",
    "start_delivery",
    "content_start",
    "topic_submit",
}
# 文档金样例引用的 workflow 可能领先于 registry 版本
_LEGACY_DOC_WORKFLOWS = frozenset({
    "commercial_solution",
    "finance_followup",
    "video_publish",
})


def _load(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_a2a_task(data: dict, reg: dict, known_roles: set[int], name: str) -> list[str]:
    errors: list[str] = []
    prefix = name

    for field in ("task_id", "intent", "initiator", "mode", "tier"):
        if field not in data:
            errors.append(f"{prefix}: 缺少 {field}")

    tid = data.get("task_id", "")
    if tid and not TASK_ID.match(tid):
        errors.append(f"{prefix}: task_id 格式非法")

    if data.get("protocol_version") and not str(data["protocol_version"]).startswith("mailbus-a2a/"):
        errors.append(f"{prefix}: protocol_version 须 mailbus-a2a/*")

    for step in data.get("planned_chain") or []:
        rt = step.get("role_type")
        if rt not in known_roles:
            errors.append(f"{prefix}: planned_chain role_type={rt} 未知")

    wf_ext = (data.get("extensions") or {}).get("mailbus.workflow") or {}
    wf_id = wf_ext.get("workflow_id")
    if wf_id:
        if wf_id not in (reg.get("workflows") or {}):
            if wf_id not in _LEGACY_DOC_WORKFLOWS:
                errors.append(f"{prefix}: workflow_id={wf_id!r} 不在 registry")
        elif wf_id not in _LEGACY_DOC_WORKFLOWS:
            gates = wf_ext.get("gates") or []
            reg_gates = {
                g["gate_id"] for g in (reg["workflows"][wf_id].get("gates") or [])
            }
            for g in gates:
                gid = g.get("gate_id")
                if gid and gid not in reg_gates:
                    errors.append(f"{prefix}: gate_id={gid!r} 不在 workflow {wf_id}")

    return errors


def _validate_intake(data: dict, name: str) -> list[str]:
    errors: list[str] = []
    prefix = name

    iid = data.get("intake_id", "")
    if not INTAKE_ID.match(iid):
        errors.append(f"{prefix}: intake_id 格式须 intake-YYYYMMDD-xxxxxx")

    for field in ("source_platform", "title", "score", "decision", "created_at", "updated_at"):
        if field not in data:
            errors.append(f"{prefix}: 缺少 {field}")

    for g in data.get("commercial_gates") or []:
        gid = g.get("gate_id")
        if gid not in GATE_IDS:
            errors.append(f"{prefix}: commercial_gates gate_id={gid!r} 非法")
        if g.get("status") not in ("pending", "approved", "skipped", "denied", None):
            errors.append(f"{prefix}: gate {gid} status 非法")

    return errors


def _validate_human_queue(data: dict, name: str) -> list[str]:
    errors: list[str] = []
    prefix = name
    if "items" not in data:
        errors.append(f"{prefix}: 缺少 items 数组")
        return errors
    for item in data["items"]:
        for field in ("id", "type", "status", "title", "task_id"):
            if field not in item:
                errors.append(f"{prefix}: item 缺少 {field}")
    return errors


def _validate_step_result(data: dict, name: str) -> list[str]:
    errors: list[str] = []
    for field in ("task_id", "step_id", "agent", "role_type", "conclusion", "summary", "timestamp"):
        if field not in data:
            errors.append(f"{name}: 缺少 {field}")
    return errors


def _validate_golden_a2a_path(data: dict, name: str) -> list[str]:
    errors: list[str] = []
    prefix = name
    if data.get("schema") != "mailbus-golden-a2a-path-v1":
        errors.append(f"{prefix}: schema 须 mailbus-golden-a2a-path-v1")
    path = data.get("path")
    if path not in ("a", "b", "c", "d"):
        errors.append(f"{prefix}: path 须 a|b|c|d")
    if "scenario" not in data:
        errors.append(f"{prefix}: 缺少 scenario")
    if path in ("a", "b", "d") and "canonical_step_result" not in data:
        errors.append(f"{prefix}: 缺少 canonical_step_result")
    if path == "b" and not (data.get("transport_audit") or {}).get("a2a_retries_exhausted"):
        errors.append(f"{prefix}: path b 须 a2a_retries_exhausted")
    if path == "c" and "human_queue" not in data:
        errors.append(f"{prefix}: path c 须 human_queue")
    sr = data.get("canonical_step_result") or {}
    if sr:
        errors.extend(_validate_step_result(sr, f"{prefix}/canonical_step_result"))
    return errors


def _validate_code_review_report(data: dict, name: str) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != "code-review-report-v1":
        errors.append(f"{name}: schema 须 code-review-report-v1")
    for field in ("commit_sha", "aggregate_status", "layers", "timestamp"):
        if field not in data:
            errors.append(f"{name}: 缺少 {field}")
    return errors


def _validate_planner_output(data: dict, name: str) -> list[str]:
    errors: list[str] = []
    if "planned_chain" not in data or "plan_meta" not in data:
        errors.append(f"{name}: 缺少 planned_chain 或 plan_meta")
    return errors


def _validate_google_a2a_inbound(data: dict, name: str) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != "google-a2a-inbound-v1":
        errors.append(f"{name}: schema 须 google-a2a-inbound-v1")
    req = data.get("request") or {}
    if "message" not in req:
        errors.append(f"{name}: request 缺少 message")
        return errors
    try:
        sys.path.insert(0, str(ROOT))
        from lib.core.a2a.a2a_mapper import from_a2a_task_create

        env = from_a2a_task_create(req)
    except Exception as exc:
        errors.append(f"{name}: from_a2a_task_create 失败: {exc}")
        return errors
    expected = data.get("expected_envelope") or {}
    for key, val in expected.items():
        if env.get(key) != val:
            errors.append(f"{name}: expected_envelope.{key}={val!r} got {env.get(key)!r}")
    return errors


def _validate_route_next(data: dict, known_roles: set[int], name: str) -> list[str]:
    errors: list[str] = []
    if "suggested_step" not in data:
        errors.append(f"{name}: 缺少 suggested_step")
        return errors
    rt = data["suggested_step"].get("role_type")
    if rt is not None and rt not in known_roles:
        errors.append(f"{name}: role_type={rt} 未知")
    return errors


def validate_file(path: Path, reg: dict, known_roles: set[int]) -> list[str]:
    data = _load(path)
    name = path.name
    if name.startswith("a2a-task") or name.startswith("task-created"):
        if name.startswith("task-created"):
            data = data.get("task") or data
        return _validate_a2a_task(data, reg, known_roles, name)
    if name.startswith("a2a-step-result"):
        return _validate_step_result(data, name)
    if name.startswith("a2a-planner-output"):
        return _validate_planner_output(data, name)
    if name.startswith("a2a-route-next"):
        return _validate_route_next(data, known_roles, name)
    if name.startswith("order-intake"):
        return _validate_intake(data, name)
    if name.startswith("human-queue"):
        return _validate_human_queue(data, name)
    if name.startswith("golden-a2a-path"):
        return _validate_golden_a2a_path(data, name)
    if name.startswith("code-review-report"):
        return _validate_code_review_report(data, name)
    if name.startswith("google-a2a-"):
        if "request" not in data:
            return [f"{name}: 缺少 request"]
        if name == "google-a2a-inbound-create.json":
            return _validate_google_a2a_inbound(data, name)
        return []
    if name.startswith("opencode-replies"):
        if "payload" not in data:
            return [f"{name}: 缺少 payload"]
        return []
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 store/examples JSON")
    ap.add_argument("--examples", type=Path, default=EXAMPLES)
    args = ap.parse_args()

    if not args.examples.is_dir():
        print(f"ERROR: missing {args.examples}", file=sys.stderr)
        return 2

    reg = _load(REGISTRY)
    roles = _load(ROLE_TYPES)
    known_roles = {int(k) for k in roles.get("roles", {})}

    files = sorted(p for p in args.examples.glob("*.json"))
    if not files:
        print("ERROR: no example JSON files", file=sys.stderr)
        return 2

    all_errors: list[str] = []
    for path in files:
        errs = validate_file(path, reg, known_roles)
        mark = "FAIL" if errs else "OK"
        print(f"  [{mark}] {path.name}")
        all_errors.extend(errs)

    if all_errors:
        print("\nERRORS:", file=sys.stderr)
        for e in all_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"ALL EXAMPLES OK ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
