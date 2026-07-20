#!/usr/bin/env python3
"""Bootstrap mail/skills/roles archetypes and overlays (one-time generator)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLES = ROOT / "skills" / "roles"

AGENT_ARCHETYPES: dict[str, str] = {
    "dali": "coding-executor",
    "lingyun": "coding-pro",
    "lingyan": "test-engineer",
    "lingjian": "code-reviewer",
    "lingzhao": "spec-designer",
    "xiaoqi": "orchestrator",
    "yige": "operations",
    "lingjin": "security-auditor",
    "lingxi": "tech-radar",
    "lingtuo": "market-expansion",
    "lingxun": "patroller",
    "lingxiao": "tech-lead",
    "lingzhang": "finance-followup",
}

ARCHETYPE_META: dict[str, dict] = {
    "coding-executor": {
        "title": "编码执行",
        "do": "按工单实现、TDD、自测、patch 交付",
        "dont": "方案设计、拆单、改架构不经灵霄",
        "sparc": "A→R（确认架构、编码+自审）",
    },
    "coding-pro": {
        "title": "Pro 编码",
        "do": "跨文件 refactor、复杂实现、msg-results 举证",
        "dont": "拆单、验收、日常 flash 小改（归 dali）",
        "sparc": "A→R（pro 长工单）",
    },
    "test-engineer": {
        "title": "测试工程师",
        "do": "pytest/Playwright/k6、测试报告 JSON",
        "dont": "写业务代码（除非工单明确允许）",
        "sparc": "R 阶段测试签字",
    },
    "code-reviewer": {
        "title": "代码审查",
        "do": "PR/patch review、结构化审查报告",
        "dont": "替大力写功能代码",
        "sparc": "R:review",
    },
    "spec-designer": {
        "title": "方案设计",
        "do": "brief、ADR、plans、架构决策",
        "dont": "日常编码、测试执行",
        "sparc": "S（Specification）",
    },
    "orchestrator": {
        "title": "调度管家",
        "do": "拆单、FSM、验收、派活",
        "dont": "micromanage 编码细节、deep 编码",
        "sparc": "P + C（Pseudocode、Completion）",
    },
    "operations": {
        "title": "运营",
        "do": "内容、公域运营、发布记录",
        "dont": "deep 编码、架构决策",
        "sparc": "按工单执行运营 deliverable",
    },
    "security-auditor": {
        "title": "安全审计",
        "do": "安全评估、审计报告、架构安全建议",
        "dont": "业务编码、常规 dev review",
        "sparc": "审计轮次签字",
    },
    "tech-radar": {
        "title": "技术雷达",
        "do": "Trending 扫描、工具评估、技能缺口报告",
        "dont": "写代码、派活、架构拍板",
        "sparc": "调研 deliverable → 灵昭审核",
    },
    "market-expansion": {
        "title": "市场拓展",
        "do": "商机扫描、pursue 评分、商务线索",
        "dont": "编码、合同数字执行",
        "sparc": "商前线索 → 灵昭审",
    },
    "patroller": {
        "title": "巡检",
        "do": "按 patroller.md SOP 巡检、告警",
        "dont": "修 bug、编码",
        "sparc": "巡检报告 deliverable",
    },
    "tech-lead": {
        "title": "技术负责人",
        "do": "架构把关、patch 合并、技术决策升级",
        "dont": "日常全部编码（派 dali/lingyun）",
        "sparc": "A 确认 + patch 合并",
    },
    "finance-followup": {
        "title": "财务跟进",
        "do": "账期、发票跟进、财务记录",
        "dont": "商务谈判、编码",
        "sparc": "财务 deliverable",
    },
}

OVERLAY_SPARC: dict[str, str] = {
    "dali": "[P→A] [A→R] [R:review]",
    "lingyun": "[A→R] pro 长工单",
    "lingyan": "测试任务 → msg-results 报告",
    "lingjian": "[R:review] 审查报告",
    "lingzhao": "[S] 方案定稿",
    "xiaoqi": "[P] [C] 拆单验收",
    "yige": "运营 deliverable",
    "lingjin": "安全审计轮次",
    "lingxi": "雷达报告",
    "lingtuo": "商机 pursue",
    "lingxun": "巡检 SOP",
    "lingxiao": "架构确认 + patch 合并",
    "lingzhang": "账期跟进",
}


def write_archetype(name: str, meta: dict) -> None:
    base = ROLES / "archetypes" / name
    base.mkdir(parents=True, exist_ok=True)
    title = meta["title"]
    (base / "SPEC.md").write_text(
        f"# L2 — {title} Archetype Spec\n\n> **Layer**: L2 · **Archetype**: `{name}`\n\n",
        encoding="utf-8",
    )
    (base / "boundaries.md").write_text(
        f"# L2 — {title} 边界\n\n## 做\n\n- {meta['do']}\n\n## 不做\n\n- {meta['dont']}\n",
        encoding="utf-8",
    )
    (base / "conventions.md").write_text(
        f"# L2 — {title} 规范\n\n交付物格式见 overlay 与 L1 delivery.md。\n",
        encoding="utf-8",
    )
    (base / "checklist.md").write_text(
        f"# L2 — {title} 自检\n\n- [ ] 未越权其他工种\n- [ ] 交付物符合 L1 SoT\n",
        encoding="utf-8",
    )
    (base / "references" / "sparc-mapping.md").parent.mkdir(parents=True, exist_ok=True)
    (base / "references" / "sparc-mapping.md").write_text(
        f"# SPARC — {title}\n\n本工种 SPARC 段：**{meta['sparc']}**\n\n完整流程见 `mail/docs/agent-layer-spec.md`。\n",
        encoding="utf-8",
    )
    skill_id = f"role-{name}"
    (base / "SKILL.md").write_text(
        f"""---
name: {skill_id}
description: >
  L2 工种边界：{title}。做：{meta['do'][:80]}…
always: true
type: role_archetype
layer: L2
archetype: {name}
---

# Role — {title}（L2 archetype）

## 边界

- **做**: {meta['do']}
- **不做**: {meta['dont']}

## SPARC

{meta['sparc']}

## 按需 Read

| 文件 | 内容 |
|------|------|
| [boundaries.md](boundaries.md) | 完整边界 |
| [references/sparc-mapping.md](references/sparc-mapping.md) | SPARC 段 |

Per-agent overlay → `mail/skills/roles/overlays/{{agent}}/SKILL.md`
""",
        encoding="utf-8",
    )


def write_overlay(agent: str, archetype: str) -> None:
    base = ROLES / "overlays" / agent
    base.mkdir(parents=True, exist_ok=True)
    meta = ARCHETYPE_META[archetype]
    sparc = OVERLAY_SPARC.get(agent, meta["sparc"])
    (base / "SKILL.md").write_text(
        f"""---
name: role-overlay-{agent}
description: >
  L2 {agent} 专属 overlay。extends {archetype}。
always: true
type: role_overlay
layer: L2
extends: {archetype}
agent_id: {agent}
---

# Role Overlay — {agent}

> **extends**: `role-{archetype}` · **identity**: `mail/skills/roles/overlays/{agent}/SKILL.md`

## SPARC 门禁

{sparc}

## 听命链

见 identity 文件。

## 装备 skill（L3 按需）

见 `roles-skills-map.md` 与 `store/agents/json/skills-index.json`。

## 开工前（编码类）

1. memory search decision/checklist
2. cost report（如适用）
3. 加载 L3 domain skills（工单指定）
""",
        encoding="utf-8",
    )


def main() -> None:
    for name, meta in ARCHETYPE_META.items():
        write_archetype(name, meta)
    for agent, arch in AGENT_ARCHETYPES.items():
        write_overlay(agent, arch)
    print(f"Wrote {len(ARCHETYPE_META)} archetypes, {len(AGENT_ARCHETYPES)} overlays")


if __name__ == "__main__":
    main()
