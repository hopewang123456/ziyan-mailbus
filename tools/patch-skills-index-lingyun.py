#!/usr/bin/env python3
"""skills-index 补全 lingyun / claude_code 交付链。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "store", "agents", "json", "skills-index.json")

LINGYUN_SKILLS = [
    {"id": "test-driven-development", "path": ".codex/skills/software-development/test-driven-development/SKILL.md", "type": "codex_skill"},
    {"id": "systematic-debugging", "path": ".codex/skills/software-development/systematic-debugging/SKILL.md", "type": "codex_skill"},
    {"id": "github-pr-workflow", "path": ".codex/skills/github/github-pr-workflow/SKILL.md", "type": "codex_skill"},
]

LINGYAN_SKILLS = [
    {"id": "test-driven-development", "path": ".codex/skills/software-development/test-driven-development/SKILL.md", "type": "codex_skill"},
    {"id": "systematic-debugging", "path": ".codex/skills/software-development/systematic-debugging/SKILL.md", "type": "codex_skill"},
    {"id": "github-code-review", "path": ".codex/skills/github/github-code-review/SKILL.md", "type": "codex_skill"},
]


def main() -> None:
    with open(INDEX, encoding="utf-8") as f:
        d = json.load(f)
    agents = d.setdefault("agents", {})
    agents["lingyun"] = {
        "role_types": [8],
        "framework": "claude_code",
        "skills": LINGYUN_SKILLS,
    }
    lingyan = agents.setdefault("lingyan", {})
    lingyan["framework"] = "claude_code"
    lingyan["skills"] = LINGYAN_SKILLS
    d["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print("patched", INDEX)


if __name__ == "__main__":
    main()
