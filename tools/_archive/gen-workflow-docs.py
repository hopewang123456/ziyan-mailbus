#!/usr/bin/env python3
"""从 registry.json 生成 store/workflows/README.md（人类可读目录）。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "store" / "workflows" / "registry.json"
OUT = ROOT / "store" / "workflows" / "README.md"
ROLE_TYPES = ROOT / "store" / "roles" / "json" / "role-types.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _role_label(role_types: dict, rt: int) -> str:
    r = role_types["roles"][str(rt)]
    d = r.get("display") or {}
    return f"{rt} `{r['key']}` · {d.get('zh', '')}"


def gen_readme(reg: dict, role_types: dict) -> str:
    lines = [
        "# Workflow 注册表（审阅用）",
        "",
        f"> **自动生成** · `{date.today().isoformat()}` · 源：`registry.json`",
        "> **勿手改流程表**；改 JSON 后运行 `python tools/gen-workflow-docs.py`",
        "",
        f"版本 **{reg.get('version', '?')}** · 更新 **{reg.get('updated_at', '?')}**",
        "",
        "## 一览",
        "",
        "| workflow_id | 中文 | mode | task_types | 闸门数 |",
        "|-------------|------|------|------------|--------|",
    ]
    for wf_id, wf in sorted((reg.get("workflows") or {}).items()):
        disp = (wf.get("display") or {}).get("zh", "")
        mode = wf.get("mode", "")
        tts = ", ".join(wf.get("task_types") or [])
        gates = len(wf.get("gates") or [])
        lines.append(f"| `{wf_id}` | {disp} | {mode} | {tts} | {gates} |")

    defaults = reg.get("defaults") or {}
    if defaults:
        lines += [
            "",
            "## 默认",
            "",
            f"- 未知 task_type → `{defaults.get('unknown_task_type_workflow', '?')}`",
            f"- LLM 路由须人工确认 → `{defaults.get('llm_route_require_human_confirm', True)}`",
        ]

    for wf_id, wf in sorted((reg.get("workflows") or {}).items()):
        disp = (wf.get("display") or {}).get("zh", wf_id)
        lines += ["", f"## `{wf_id}` — {disp}", ""]
        if wf.get("description"):
            lines.append(wf["description"])
            lines.append("")

        gates = {g["gate_id"]: g for g in (wf.get("gates") or [])}
        if gates:
            lines += ["### 闸门", "", "| gate_id | 中文 | actor | 附件≥ |", "|---------|------|-------|-------|"]
            for gid, g in gates.items():
                zh = (g.get("display") or {}).get("zh", "")
                actor = g.get("actor", "")
                att = g.get("required_attachments_min", 0)
                lines.append(f"| `{gid}` | {zh} | {actor} | {att} |")
            lines.append("")

        phases = wf.get("phases") or []
        if phases:
            lines += ["### 阶段", ""]
            for phase in phases:
                pid = phase["id"]
                pzh = (phase.get("display") or {}).get("zh", pid)
                entry = phase.get("entry_gate_id")
                entry_note = f" · 入口闸门 `{entry}`" if entry else ""
                lines.append(f"**{pid}** ({pzh}){entry_note}")
                for step in phase.get("steps") or []:
                    nt = step.get("node_type")
                    if nt == "agent":
                        rt = step.get("role_type")
                        sub = f" / {step['sub']}" if step.get("sub") else ""
                        lines.append(f"- agent · {_role_label(role_types, rt)}{sub}")
                    elif nt == "tool":
                        lines.append(f"- tool · `{step.get('tool_id')}`")
                    else:
                        lines.append(f"- {nt}")
                after = phase.get("after_agent") or {}
                if after.get("gate_id"):
                    lines.append(f"- → blocked · 闸门 `{after['gate_id']}`")
                lines.append("")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    reg = _load(REGISTRY)
    roles = _load(ROLE_TYPES)
    OUT.write_text(gen_readme(reg, roles), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
