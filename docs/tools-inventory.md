# mail/tools 盘点

> 更新：2026-06-26 · Phase 6 瘦身（#44–#46 + legacy 删）

## mail 根目录（Phase 6 瘦身后）

| 类别 | 保留 |
|------|------|
| 核心 CLI | `bus.py`、`pyproject.toml`、`mailbus-send`、`mailbus-memory-bridge.py` |
| 文档 | `README.md`、`README.zh.md`、`LICENSE`、`CHANGELOG.md`、`wipe-manifest.json` |
| 核心目录 | `lib/`、`store/`、`access/`、`skills/`、`rules/`、`config/`、`org/`、`tools/`、`docs/`、`docker-agents/`、`tests/`、`examples/` |

已归档至 `tools/_archive/`：`mailbus-boot.sh`、`STANDARD_PROCEDURE.md`、`gateway_mail.py` 等。  
Watchdog 脚本迁至 `docker-agents/`；`mailbus-log-rotate.py` → `tools/ops/`。

## 支持脚本（tools 根目录 · 20）

| 脚本 | 用途 |
|------|------|
| `init-store.py` | store 初始化 / config 合并 |
| `write_reorg_risks.py` | 风险登记写回 |
| `validate-agent-layers.py` | L0–L2 skills 校验 |
| `validate-order-intake.py` | 商前 intake schema |
| `validate-workflows.py` | workflow registry |
| `validate-scheduler.py` | scheduler jobs |
| `validate-examples.py` | examples JSON |
| `check-preflight.py` | 启动前检查 |
| `sync-all-agent-layers.py` | 全 agent sync |
| `sync-claude-agent-context.py` | Claude agent 上下文 |
| `sync_framework_workspace_skills.py` | framework workspace skills |
| `sync_codex_agent_skills.py` | Codex skills |
| `generate-compose-volumes.py` | compose volume 生成 |
| `live-dali-opencode-e2e.py` | live dali E2E |
| `verify-live-dali-e2e.py` | live E2E 验收 |
| `collect-pipeline-postmortem.py` | pipeline 事故采集 |
| `restart-mailbus.py` | mailbus 重启 |
| `patch-skills-index-framework.py` | skills-index 补全（`start-team.sh`） |
| `resolve-agent-cli.py` | agent CLI 解析 |
| `bootstrap-role-specs.py` | role spec bootstrap |

## 根目录 runtime（10 · scheduler + pipeline + E2E + entrypoint sync）

| 脚本 | 引用方 |
|------|--------|
| `platform-scout.py` | `lib/jobs.py` scheduler |
| `pipeline-watchdog.py` | scheduler |
| `repair-pipeline-stuck.py` | scheduler + `base.json` |
| `pipeline-push-step1.py` | `base.json` pipeline_ops |
| `pipeline-e2e-regression.py` | `mailbus-pipeline-e2e.sh` |
| `run-game-lvup-e2e.py` | 验收 / TEST_PLAN |
| `test-automation-e2e.py` | 自动化 E2E |
| `sync-opencode-framework-skill.sh` | opencode entrypoint |
| `sync-openclaw-framework-skill.sh` | openclaw entrypoint |
| `sync-hermes-framework-skill.sh` | hermes entrypoint |

**根目录合计：30 文件**

## `tools/ops/`（docker-agents · smoke · 验收 · watchdog · 40+ 项）

`mailbus-log-rotate.py` · `launch-agent.sh` · `task-create-envelope.py` · `watch-task-pipeline.py` · smoke/launch/setup 脚本等。详见 `tools/ops/README.md`。

## 其它目录

| 位置 | 用途 |
|------|------|
| `mail/tools/_incidents/` | postmortem 一次性 patch（22 项） |
| `mail/tools/_archive/` | 无引用历史脚本（~95 项） |
| `mail/docker-agents/` | compose + start-team + health/e2e |
| `E:/ai_tools/scripts/` | WSL/Windows 桌面入口 |

## P6-C01 状态

| 轮次 | 动作 | 根目录文件数 |
|------|------|-------------|
| 首批 | 22→`_incidents` · 8→`_archive` | ~150 |
| 第二批 | 90→`_archive` | 69 |
| **第四轮** | mail 根杂项→`_archive/` · legacy 三目录 git rm · `config/` 重建 | **根文件 ≤10** ✅ |
