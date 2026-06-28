#!/usr/bin/env python3
"""校验 store 下 JSON Schema 与关键 SoT 文件存在性。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = [
    ("rules/a2a-task.schema.json", "object"),
    ("rules/a2a-step-result.schema.json", "object"),
    ("rules/a2a-planner-output.schema.json", "object"),
    ("rules/human-queue.schema.json", "object"),
    ("rules/order-intake.schema.json", "object"),
    ("workflows/registry.schema.json", "object"),
    ("roles/json/role-types.json", "object"),
    ("roles/json/role-flow.json", "object"),
    ("roles/json/roster.json", "object"),
    ("roles/json/capabilities.json", "object"),
    ("roles/json/agent-registry.json", "object"),
    ("workflows/registry.json", "object"),
    ("dispatch/role-round-robin.json", "object"),
    ("billing/billing-accounts.schema.json", "object"),
]


def main() -> int:
    errors: list[str] = []
    for rel, kind in CHECKS:
        path = ROOT / "store" / rel
        if not path.is_file():
            errors.append(f"missing {rel}")
            print(f"  [FAIL] {rel}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"invalid json {rel}: {e}")
            print(f"  [FAIL] {rel} (json)")
            continue
        if kind == "object" and not isinstance(data, dict):
            errors.append(f"{rel} not object")
            print(f"  [FAIL] {rel} (type)")
        else:
            print(f"  [OK] {rel}")

    # cross-check workflow count
    reg = json.loads((ROOT / "store/workflows/registry.json").read_text(encoding="utf-8"))
    wf_count = len(reg.get("workflows") or {})
    if wf_count < 6:
        errors.append(f"registry workflows={wf_count} expected >=6")

    if errors:
        print("\nERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"ALL SCHEMAS OK ({len(CHECKS)} files, {wf_count} workflows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
