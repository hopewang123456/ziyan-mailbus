#!/usr/bin/env python3
"""校验 store/leads/order-intake.json 是否符合 order-intake.schema.json（轻量校验，无 jsonschema 依赖）。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_CONFIG = ROOT / "config" / "intake" / "bridge.json"
SCHEMA_SO_T = ROOT / "rules" / "schemas" / "order-intake.schema.json"
INTAKE_ID_RE = re.compile(r"^intake-[0-9]{8}-[a-z0-9]{6}$")
DECISIONS = {"pending", "pursue", "watch", "reject", "handed_to_lingzhao"}
STAGES = {
    "analyzed", "contacting", "qualified", "designing",
    "await_customer", "delivery", "closed",
}
GATE_IDS = {
    "contact_done", "req_to_lingzhao", "customer_design_ok",
    "start_delivery", "content_start",
}
GATE_STATUS = {"pending", "approved", "skipped", "denied"}
CONTACT_STATUS = {"not_contacted", "sent", "replied", "call_done", "unreachable"}
CONTENT_PLATFORMS = {"douyin", "xiaohongshu", "wechat", "channels", "bilibili"}


def _err(errors: list[str], idx: int, msg: str) -> None:
    errors.append(f"[{idx}] {msg}")


def _check_intake_record(rec: dict, idx: int, errors: list[str]) -> None:
    if not isinstance(rec, dict):
        _err(errors, idx, "record must be object")
        return

    for field in ("intake_id", "source_platform", "title", "score", "decision", "created_at", "updated_at"):
        if field not in rec:
            _err(errors, idx, f"missing required field '{field}'")

    iid = rec.get("intake_id")
    if iid is not None and (not isinstance(iid, str) or not INTAKE_ID_RE.match(iid)):
        _err(errors, idx, "intake_id must match intake-YYYYMMDD-xxxxxx")

    title = rec.get("title")
    if title is not None and (not isinstance(title, str) or len(title.strip()) < 3):
        _err(errors, idx, "title must be string with minLength 3")

    score = rec.get("score")
    if score is not None and (not isinstance(score, int) or score < 0 or score > 100):
        _err(errors, idx, "score must be integer 0..100")

    decision = rec.get("decision")
    if decision is not None and decision not in DECISIONS:
        _err(errors, idx, f"decision must be one of {sorted(DECISIONS)}")

    stage = rec.get("stage")
    if stage is not None and stage not in STAGES:
        _err(errors, idx, f"stage invalid: {stage}")

    contact = rec.get("contact")
    if contact is not None:
        if not isinstance(contact, dict):
            _err(errors, idx, "contact must be object")
        elif (contact.get("status") or "") not in CONTACT_STATUS:
            _err(errors, idx, "contact.status invalid")

    gates = rec.get("commercial_gates")
    if gates is not None:
        if not isinstance(gates, list):
            _err(errors, idx, "commercial_gates must be array")
        else:
            for gi, gate in enumerate(gates):
                if not isinstance(gate, dict):
                    _err(errors, idx, f"commercial_gates[{gi}] must be object")
                    continue
                if gate.get("gate_id") not in GATE_IDS:
                    _err(errors, idx, f"commercial_gates[{gi}].gate_id invalid")
                if gate.get("status") not in GATE_STATUS:
                    _err(errors, idx, f"commercial_gates[{gi}].status invalid")

    hint = rec.get("content_hint")
    if hint is not None and isinstance(hint, dict):
        plats = hint.get("platforms")
        if plats is not None:
            if not isinstance(plats, list):
                _err(errors, idx, "content_hint.platforms must be array")
            else:
                for p in plats:
                    if p not in CONTENT_PLATFORMS:
                        _err(errors, idx, f"content_hint.platforms invalid value: {p}")

    tech = rec.get("tech_stack")
    if tech is not None and (not isinstance(tech, list) or any(not isinstance(x, str) for x in tech)):
        _err(errors, idx, "tech_stack must be array of strings")

    tags = rec.get("tags")
    if tags is not None and (not isinstance(tags, list) or any(not isinstance(x, str) for x in tags)):
        _err(errors, idx, "tags must be array of strings")


def validate_intake_file(path: Path) -> tuple[list[str], int]:
    errors: list[str] = []
    if not path.is_file():
        return [f"missing {path}"], 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid json: {exc}"], 0
    if not isinstance(data, list):
        return ["order-intake.json must be a JSON array"], 0

    seen_ids: set[str] = set()
    for idx, rec in enumerate(data):
        if isinstance(rec, dict):
            iid = rec.get("intake_id")
            if isinstance(iid, str):
                if iid in seen_ids:
                    _err(errors, idx, f"duplicate intake_id {iid}")
                seen_ids.add(iid)
        _check_intake_record(rec if isinstance(rec, dict) else {}, idx, errors)
    return errors, len(data)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Validate order-intake.json against schema rules")
    ap.add_argument("--data-dir", default=str(ROOT / "store"))
    args = ap.parse_args()
    intake_path = Path(args.data_dir) / "leads" / "order-intake.json"
    schema_path = Path(args.data_dir) / "rules" / "order-intake.schema.json"
    if not schema_path.is_file() and SCHEMA_SO_T.is_file():
        schema_path = SCHEMA_SO_T

    if not schema_path.is_file():
        print(f"  [FAIL] missing schema {schema_path}", file=sys.stderr)
        return 1

    if not BRIDGE_CONFIG.is_file():
        print(f"  [FAIL] missing intake bridge SoT {BRIDGE_CONFIG}", file=sys.stderr)
        return 1
    try:
        bridge = json.loads(BRIDGE_CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"  [FAIL] invalid bridge config: {exc}", file=sys.stderr)
        return 1
    if not isinstance(bridge, dict) or "enabled" not in bridge:
        print("  [FAIL] config/intake/bridge.json must be object with 'enabled'", file=sys.stderr)
        return 1

    errors, count = validate_intake_file(intake_path)
    if errors:
        print(f"  [FAIL] order-intake.json ({count} records)", file=sys.stderr)
        for e in errors:
            print(f"    - {e}", file=sys.stderr)
        return 1
    print(f"  [OK] order-intake.json ({count} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
