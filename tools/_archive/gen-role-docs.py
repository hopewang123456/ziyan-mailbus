#!/usr/bin/env python3
"""Generate store/roles/md/*.md from store/roles/json/*.json (human review only)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_DIR = ROOT / "store" / "roles" / "json"
MD_DIR = ROOT / "store" / "roles" / "md"


def _load(name: str) -> dict:
    return json.loads((JSON_DIR / name).read_text(encoding="utf-8"))


def _role_label(role_types: dict, rt: int) -> str:
    r = role_types["roles"][str(rt)]
    d = r.get("display") or {}
    return f"{rt} `{r['key']}` · {d.get('zh', '')} / {d.get('en', '')}"


def gen_catalog(role_types: dict) -> str:
    lines = [
        "# 角色类型目录（审阅用）",
        "",
        f"> **自动生成** · `{date.today().isoformat()}` · 源：`json/role-types.json`",
        "> **勿手改映射表**；改 JSON 后运行 `python tools/gen-role-docs.py`",
        "",
        "| role_type | key | 中文 | English | candidates | SLA |",
        "|-----------|-----|------|---------|------------|-----|",
    ]
    for k, v in sorted(role_types["roles"].items(), key=lambda x: int(x[0])):
        d = v.get("display") or {}
        cands = ", ".join(v.get("candidates") or [])
        sla = v.get("default_sla_minutes", "")
        lines.append(f"| {k} | {v['key']} | {d.get('zh','')} | {d.get('en','')} | {cands} | {sla}m |")
    lines += ["", "## 结论码", ""]
    lines.append("| code | 中文 | English |")
    lines.append("|------|------|---------|")
    for code, d in (role_types.get("conclusions") or {}).items():
        lines.append(f"| {code} | {d.get('zh','')} | {d.get('en','')} |")
    lines.append("")
    return "\n".join(lines)


def gen_flow_guide(role_types: dict, flow: dict) -> str:
    lines = [
        "# 角色流转指南（审阅用）",
        "",
        f"> **自动生成** · 源：`json/role-flow.json` + `json/role-types.json`",
        "",
        "## 转移表",
        "",
        "| from | conclusion | to |",
        "|------|------------|-----|",
    ]
    for t in flow.get("transitions") or []:
        fr = _role_label(role_types, t["from_role_type"])
        to = "—" if t.get("to_role_type") is None else _role_label(role_types, t["to_role_type"])
        lines.append(f"| {fr} | {t['conclusion']} | {to} |")
    lines += ["", "## 终态", ""]
    for term in flow.get("terminal") or []:
        lines.append(f"- {_role_label(role_types, term['role_type'])} + `{term['conclusion']}`")
    lines.append("")
    return "\n".join(lines)


def gen_roster_guide(role_types: dict, roster: dict) -> str:
    lines = [
        "# 团队编制（审阅用）",
        "",
        f"> **自动生成** · 源：`json/roster.json`",
        "",
        f"**{roster.get('team_name', '')}** · headcount={roster.get('headcount', 0)}",
        "",
        "| agent | 中文 | role_types | framework | port |",
        "|-------|------|------------|-----------|------|",
    ]
    for m in roster.get("members") or []:
        d = m.get("display") or {}
        rts = ", ".join(str(x) for x in (m.get("role_types") or []))
        lines.append(
            f"| {m['id']} | {d.get('zh','')} | {rts} | {m.get('framework','')} | {m.get('port') or '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    MD_DIR.mkdir(parents=True, exist_ok=True)
    role_types = _load("role-types.json")
    flow = _load("role-flow.json")
    roster = _load("roster.json")
    (MD_DIR / "catalog.md").write_text(gen_catalog(role_types), encoding="utf-8")
    (MD_DIR / "flow-guide.md").write_text(gen_flow_guide(role_types, flow), encoding="utf-8")
    (MD_DIR / "roster-guide.md").write_text(gen_roster_guide(role_types, roster), encoding="utf-8")
    print("Generated:", MD_DIR / "catalog.md", MD_DIR / "flow-guide.md", MD_DIR / "roster-guide.md")


if __name__ == "__main__":
    main()
