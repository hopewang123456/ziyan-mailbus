#!/usr/bin/env python3
"""Phase 2 directory migration — run once, idempotent-ish via overwrite."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

MAIL = Path(__file__).resolve().parent.parent
REPO = MAIL.parent
BACKUP_ORG = MAIL / "store" / "roles" / "json"
TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

ACCESS_FW = {
    "hermes_profile": "hermes",
    "codex": "codex",
    "claude_code": "claude_code",
    "opencode": "opencode",
    "openclaw": "openclaw",
}

FRAMEWORKS = [
    "hermes_profile",
    "codex",
    "claude_code",
    "opencode",
    "openclaw",
    "cline",
    "cursor",
]


def ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def copy_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        return
    ensure(dst.parent)
    shutil.copy2(src, dst)


def copy_adapter(framework: str, access_name: str) -> None:
    src = MAIL / "adapters" / framework / "framework-runtime"
    dst = ensure(MAIL / "access" / access_name / "adapter")
    if not src.exists():
        return
    for name in ("SPEC.md",):
        copy_file(src / name, dst / name)
    ref_src = src / "references"
    if ref_src.is_dir():
        copy_tree(ref_src, dst / "references")


def migrate_skills() -> None:
    copy_tree(MAIL / "adapters" / "_shared" / "agent-universal", MAIL / "skills" / "common" / "agent-universal")
    copy_tree(
        MAIL / "adapters" / "_shared" / "mailbus-file-protocol",
        MAIL / "skills" / "common" / "mailbus-file-protocol",
    )
    for fw in FRAMEWORKS:
        src = MAIL / "adapters" / fw / "framework-runtime"
        if src.is_dir():
            copy_tree(src, MAIL / "skills" / "frameworks" / fw)
    copy_tree(MAIL / "roles" / "archetypes", MAIL / "skills" / "roles" / "archetypes")
    copy_tree(MAIL / "roles" / "overlays", MAIL / "skills" / "roles" / "overlays")
    ensure(MAIL / "skills" / "domain")


def migrate_rules() -> None:
    common = ensure(MAIL / "rules" / "common")
    old_rules = MAIL / "rules"
    for name in (
        "execution-order.md",
        "team-secrets-policy.md",
        "iteration-protocol.md",
        "closed-loop-task-design.md",
        "model-routing.md",
        "pipeline-agent-paths.md",
        "role-flow-config.md",
    ):
        copy_file(old_rules / name, common / name)
    task_fsm = common / "task-fsm.md"
    if not task_fsm.exists():
        task_fsm.write_text(
            "# Task / Step 状态机\n\n"
            "SoT 实现：`mail/lib/task_fsm.py`。\n\n"
            "- done 仅认 `store/msg-results/{msg_id}.json`\n"
            "- 禁止 phantom 回执（只写 replies 不算完成）\n"
            "- Work Order：`store/work-orders/{task_id}/step-{step_id}.md`\n",
            encoding="utf-8",
        )
    work_order = common / "work-order-template.md"
    if not work_order.exists():
        work_order.write_text(
            "# Work Order step-{step_id}\n\n"
            "<!-- status: pending | in_progress | completed | failed -->\n\n"
            "## 目标\n\n## 约束\n\n## 验收\n",
            encoding="utf-8",
        )
    for fw in FRAMEWORKS:
        delivery = MAIL / "adapters" / fw / "framework-runtime" / "references" / "delivery.md"
        if delivery.is_file():
            copy_file(delivery, MAIL / "rules" / "frameworks" / fw / "delivery.md")
    # hermes_profile has no references/delivery.md — use legacy hermes adapter copy
    hp_delivery = MAIL / "rules" / "frameworks" / "hermes_profile" / "delivery.md"
    if not hp_delivery.is_file():
        copy_file(
            MAIL / "adapters" / "hermes" / "framework-runtime" / "references" / "delivery.md",
            hp_delivery,
        )
    archetypes = MAIL / "skills" / "roles" / "archetypes"
    if archetypes.is_dir():
        for d in archetypes.iterdir():
            if d.is_dir() and not d.name.startswith("_"):
                b = d / "boundaries.md"
                if b.is_file():
                    copy_file(b, MAIL / "rules" / "roles" / d.name / "boundaries.md")
    (MAIL / "rules" / "README.md").write_text(
        "# mail/rules — 行为规范 SoT\n\n"
        "- `common/` — 全员约束\n"
        "- `frameworks/` — 各框架 delivery / push 规范\n"
        "- `roles/` — 工种边界\n\n"
        "Skills 在 `mail/skills/`；运行时摘要可选 sync 到 `store/rules/`。\n",
        encoding="utf-8",
    )


def migrate_access_adapters() -> None:
    copy_adapter("hermes_profile", "hermes")
    for fw, access_name in ACCESS_FW.items():
        if fw != "hermes_profile":
            copy_adapter(fw, access_name)
    copy_adapter("cline", "cline")
    copy_adapter("cursor", "cursor")
    # agentmemory adapter stub
    am = ensure(MAIL / "access" / "agentmemory" / "adapter")
    (am / "SPEC.md").write_text(
        "# AgentMemory Access\n\n"
        "双写桥接：`mail/lib/memory_bridge.py`。\n"
        "配置 SoT：`mail/access/agentmemory/integration.json`。\n",
        encoding="utf-8",
    )
    ensure(am / "references").mkdir(exist_ok=True)
    (am / "references" / "bridge.md").write_text(
        "See `mail/lib/memory_bridge.py` and `mail/mailbus-memory-bridge.py`.\n",
        encoding="utf-8",
    )


def docker_block(framework: str, agent_id: str, cfg: dict) -> dict | None:
    launch = cfg.get("launch") or {}
    browser = launch.get("browser") or {}
    if framework == "hermes_profile":
        port = browser.get("dashboard_port")
        block = {"service": "hermes", "profile": cfg.get("profile") or agent_id}
        if port:
            block["port"] = port
        return block
    service_map = {
        "codex": "codex-agent",
        "claude_code": "claude-agent",
        "opencode": "opencode-agent",
        "openclaw": "openclaw-agent",
    }
    svc = service_map.get(framework)
    return {"service": svc, "profile": agent_id} if svc else None


def agent_json(agent_id: str, framework: str, archetype: str, workspace: str | None, cfg: dict) -> dict:
    skills = [
        "mail/skills/common/agent-universal",
        "mail/skills/common/mailbus-file-protocol",
        f"mail/skills/frameworks/{framework}",
        f"mail/skills/roles/archetypes/{archetype}",
        f"mail/skills/roles/overlays/{agent_id}",
    ]
    rules = [
        "mail/rules/common/execution-order.md",
        "mail/rules/common/task-fsm.md",
        "mail/rules/common/team-secrets-policy.md",
        f"mail/rules/frameworks/{framework}/delivery.md",
        f"mail/rules/roles/{archetype}/boundaries.md",
    ]
    doc = {
        "schema": "mailbus-agent-v3",
        "agent_id": agent_id,
        "framework": framework,
        "archetype": archetype,
        "skills": skills,
        "rules": rules,
        "workspace": workspace or None,
    }
    docker = docker_block(framework, agent_id, cfg)
    if docker:
        doc["docker"] = docker
    return doc


def migrate_agent_json_files() -> int:
    cfg = json.loads((MAIL / "store" / "config.json").read_text(encoding="utf-8"))
    manifest = json.loads((MAIL / "identities" / "manifest.json").read_text(encoding="utf-8"))
    count = 0
    for agent_id, acfg in sorted(cfg["agents"].items()):
        fw = acfg.get("type") or manifest["members"][agent_id]["framework"]
        meta = manifest["members"][agent_id]
        archetype = meta["archetype"]
        workspace = meta.get("workspace")
        access_name = ACCESS_FW[fw]
        out_dir = ensure(MAIL / "access" / access_name / agent_id)
        out = out_dir / "agent.json"
        out.write_text(
            json.dumps(agent_json(agent_id, fw, archetype, workspace, acfg), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        count += 1
    return count


def migrate_org() -> None:
    org_json = ensure(MAIL / "org" / "json")
    for name in (
        "roster.json",
        "role-flow.json",
        "role-types.json",
        "role-responsibilities.json",
        "agent-registry.json",
        "agent-registry.schema.json",
        "capabilities.json",
    ):
        copy_file(BACKUP_ORG / name, org_json / name)
    org_md = MAIL / "org" / "ORGANIZATION.md"
    src_org = MAIL / "ORGANIZATION.md"
    if src_org.is_file():
        text = src_org.read_text(encoding="utf-8")
        text = text.replace("store/roles/json/roster.json", "org/json/roster.json")
        org_md.write_text(text, encoding="utf-8")


def migrate_config() -> None:
    cfg_root = MAIL / "config"
    ensure(cfg_root / "llm")
    ensure(cfg_root / "pipeline")
    ensure(cfg_root / "agentmemory")
    ensure(cfg_root / "review" / "semgrep")
    ensure(cfg_root / "scheduler")
    ensure(cfg_root / "agents")

    examples = {
        "llm/ollama.json": {
            "base_url": "http://127.0.0.1:11434",
            "default_model": "qwen2.5-coder:7b",
        },
        "llm/routing.json": {
            "version": "1.0.0",
            "routes": [{"match": {"complexity": "low"}, "provider": "ollama"}],
        },
        "llm/providers.json.example.json": {
            "deepseek": {"api_key_env": "DEEPSEEK_API_KEY"},
        },
        "pipeline/role_failover.json": {
            "version": "1.0.0",
            "max_failures_per_step": 2,
            "same_archetype_only": True,
        },
        "pipeline/workflow-routes.json": {
            "version": "1.0.0",
            "routes": {},
        },
        "scheduler/jobs.json": {
            "version": "1.0.0",
            "jobs": [
                {"id": "scan", "interval_seconds": 15},
                {"id": "memory-bridge", "interval_seconds": 60},
            ],
        },
    }
    for rel, obj in examples.items():
        p = cfg_root / rel
        if not p.exists():
            p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    integration = MAIL / "access" / "agentmemory" / "integration.json"
    if not integration.exists():
        integration.write_text(
            json.dumps(
                {
                    "schema": "mailbus-agentmemory-v1",
                    "team_memory_db": "/mnt/e/hermes-data/.hermes/shared-memory/team-memory.db",
                    "agentmemory_url": "http://127.0.0.1:3111",
                    "bridge": {
                        "sqlite_env": "MEMORY_BRIDGE_SQLITE",
                        "agentmemory_env": "MEMORY_BRIDGE_AGENTMEMORY",
                        "pending_dir": "store/agentmemory-pending",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    service = MAIL / "access" / "agentmemory" / "service.json"
    if not service.exists():
        service.write_text(
            json.dumps(
                {
                    "schema": "mailbus-service-v1",
                    "name": "agentmemory",
                    "compose_file": "docker-agents/agentmemory/docker-compose.iii.yml",
                    "ports": {"http": 3111, "iii": 49134},
                    "volumes": ["iii-data"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def move_dir(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    ensure(dst.parent)
    shutil.move(str(src), str(dst))


def migrate_semgrep_and_external_tools() -> None:
    semgrep_src = MAIL / "semgrep-rules"
    semgrep_dst = MAIL / "config" / "review" / "semgrep"
    if semgrep_src.is_dir():
        ensure(semgrep_dst)
        for f in semgrep_src.glob("*.yaml"):
            shutil.copy2(f, semgrep_dst / f.name)
        shutil.rmtree(semgrep_src)
    ext_src = MAIL / "external-tools"
    ext_dst = MAIL / "access" / "external-tools"
    if ext_src.is_dir() and not ext_dst.exists():
        move_dir(ext_src, ext_dst)


def cleanup() -> None:
    archived = MAIL / "lib" / "_archived"
    if archived.is_dir():
        shutil.rmtree(archived)
    old_rules = MAIL / "rules"
    for name in (
        "closed-loop-task-design.md",
        "execution-order.md",
        "iteration-protocol.md",
        "model-routing.md",
        "pipeline-agent-paths.md",
        "role-flow-config.md",
        "team-secrets-policy.md",
    ):
        p = old_rules / name
        if p.is_file():
            p.unlink()


def write_wipe_manifest() -> None:
    doc = {
        "schema": "mailbus-wipe-manifest-v1",
        "updated_at": NOW,
        "wipe": [
            "mail/store/ (runtime: deliverables, patches, replies, human-queue, agentmemory-pending, board, sent, archive, tasks, inbox)",
            "mail/logs/",
            "pollution: mail/C:, mail/E:, mail/mnt/, mail/bus/, mail/inbox/, mail/5/",
            "E:/ai_tools/store/",
            "backup-pre-merge/",
            "adapters/.sync/ (generated)",
        ],
        "preserve": [
            "team-memory.db",
            "hermes-data",
            "AgentMemory Docker volume",
            "mail/skills/",
            "mail/rules/",
            "mail/access/",
            "mail/config/",
            "mail/org/",
            ".mailbus/claude/",
            "opencode/",
            "openclaw_space/",
        ],
        "phase": 2,
    }
    (MAIL / "wipe-manifest.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_cursorignore() -> None:
    path = REPO / ".cursorignore"
    lines = [
        "# ===== 通用（几乎所有项目） =====",
        "node_modules/",
        "dist/",
        "build/",
        ".next/",
        "target/",
        "__pycache__/",
        ".pytest_cache/",
        ".ruff_cache/",
        "*.pyc",
        ".venv/",
        "venv/",
        ".git/",
        "",
        "# 运行时 / 日志 / 缓存",
        "logs/",
        "data/",
        "tmp/",
        "cache/",
        "*.log",
        "",
        "# 大体积非源码",
        "docs/assets/",
        "*.svg",
        "*.png",
        "*.pdf",
        "*.zip",
        "",
        "# 设计与历史（fix 时按需单文件打开）",
        "plans/",
        "reports/",
        "archive/",
        "",
        "# 敏感",
        ".env",
        ".env.*",
        "*.pem",
        "credentials.json",
        "",
        "# mailbus — Phase 2: 只 ignore 运行时 store，rules/ 为 SoT 不 ignore",
        "mail/store/",
        "mail/outbox/",
        "mail/patrol_reports/",
        "mail/adapters/.sync/",
        "docker-agents/node_modules/",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_phase2_manifest(agent_count: int) -> None:
    doc = {
        "phase": "2-directory-migration",
        "created": NOW,
        "agents": agent_count,
        "access_frameworks": list(set(ACCESS_FW.values())) + ["cline", "agentmemory", "cursor", "external-tools"],
        "skills_roots": ["common", "frameworks", "roles", "domain"],
        "rules_roots": ["common", "frameworks", "roles"],
    }
    ensure(MAIL / "plans")
    (MAIL / "plans" / "phase2-reorg-manifest.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    migrate_skills()
    migrate_rules()
    migrate_access_adapters()
    n = migrate_agent_json_files()
    migrate_org()
    migrate_config()
    migrate_semgrep_and_external_tools()
    cleanup()
    write_wipe_manifest()
    update_cursorignore()
    write_phase2_manifest(n)
    print(f"phase2 ok agents={n}")


if __name__ == "__main__":
    main()
