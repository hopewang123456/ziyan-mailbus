#!/usr/bin/env python3
"""校验 store/workflows/registry.json 与 role-types 一致性。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "store" / "workflows" / "registry.json"
ROLE_TYPES = ROOT / "store" / "roles" / "json" / "role-types.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_registry(reg: dict, role_types: dict) -> list[str]:
    errors: list[str] = []
    known_roles = {int(k) for k in role_types.get("roles", {})}
    workflows = reg.get("workflows") or {}

    default_wf = (reg.get("defaults") or {}).get("unknown_task_type_workflow")
    if default_wf and default_wf not in workflows:
        errors.append(f"defaults.unknown_task_type_workflow={default_wf!r} 不存在")

    task_type_map: dict[str, str] = {}
    for wf_key, wf in workflows.items():
        prefix = f"workflows.{wf_key}"
        wf_id = wf.get("id")
        if wf_id != wf_key:
            errors.append(f"{prefix}: id={wf_id!r} 与键 {wf_key!r} 不一致")

        for tt in wf.get("task_types") or []:
            prev = task_type_map.get(tt)
            if prev and prev != wf_key:
                errors.append(f"{prefix}: task_type={tt!r} 与 {prev!r} 冲突")
            task_type_map[tt] = wf_key

        gates = {g["gate_id"]: g for g in (wf.get("gates") or [])}
        phases = {p["id"]: p for p in (wf.get("phases") or [])}

        for gate_id, gate in gates.items():
            on_approve = gate.get("on_approve") or {}
            phase_id = on_approve.get("phase_id")
            if phase_id and phase_id not in phases:
                errors.append(f"{prefix}.gates.{gate_id}: phase_id={phase_id!r} 未定义")

        for phase_id, phase in phases.items():
            pfx = f"{prefix}.phases.{phase_id}"
            entry = phase.get("entry_gate_id")
            if entry and entry not in gates:
                errors.append(f"{pfx}: entry_gate_id={entry!r} 不在 gates 中")

            after = phase.get("after_agent") or {}
            gate_ref = after.get("gate_id")
            if gate_ref and gate_ref not in gates:
                errors.append(f"{pfx}: after_agent.gate_id={gate_ref!r} 不在 gates 中")

            for i, step in enumerate(phase.get("steps") or []):
                if step.get("node_type") != "agent":
                    continue
                rt = step.get("role_type")
                if rt is None:
                    errors.append(f"{pfx}.steps[{i}]: agent 步缺少 role_type")
                elif rt not in known_roles:
                    errors.append(f"{pfx}.steps[{i}]: role_type={rt} 不在 role-types.json")

        if wf.get("mode") == "llm_adaptive":
            policy = wf.get("llm_policy") or {}
            confirm = policy.get("confirm_gate_id", "llm_step_confirm")
            if confirm not in gates:
                errors.append(f"{prefix}: llm_policy.confirm_gate_id={confirm!r} 不在 gates 中")
            if not policy.get("require_human_confirm", True):
                errors.append(f"{prefix}: llm_adaptive 须 require_human_confirm=true")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 workflow registry")
    ap.add_argument("--registry", type=Path, default=REGISTRY)
    ap.add_argument("--role-types", type=Path, default=ROLE_TYPES)
    args = ap.parse_args()

    if not args.registry.is_file():
        print(f"ERROR: missing {args.registry}", file=sys.stderr)
        return 2
    if not args.role_types.is_file():
        print(f"ERROR: missing {args.role_types}", file=sys.stderr)
        return 2

    reg = _load(args.registry)
    roles = _load(args.role_types)
    errors = validate_registry(reg, roles)
    wf_count = len(reg.get("workflows") or {})

    print(f"registry: {args.registry.name} · workflows={wf_count}")
    for wf_id, wf in sorted((reg.get("workflows") or {}).items()):
        phases = len(wf.get("phases") or [])
        gates = len(wf.get("gates") or [])
        mode = wf.get("mode", "?")
        print(f"  OK  {wf_id}  mode={mode}  phases={phases}  gates={gates}")

    if errors:
        print("\nERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("ALL WORKFLOWS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
