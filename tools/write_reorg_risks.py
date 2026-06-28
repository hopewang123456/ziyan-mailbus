#!/usr/bin/env python3
"""Writer for mail/docs/reorg-risks-by-phase.md — run after risk register updates."""
from pathlib import Path

CONTENT = r'''# Mailbus 架构重组 — 分阶段风险登记

> 计划 SoT：`C:\Users\hopew\.cursor\plans\mailbus_架构重组_bbc0d4a3.plan.md`  
> 更新：2026-06-26 Phase 6 首轮 · decomposition 门禁 · tools 盘点/首批归档  
> 用途：新会话 handoff、阶段验收、§十 checklist 对照

---

## 图例

| 状态 | 含义 |
|------|------|
| ✅ 已缓解 | 该阶段内已处理或风险已消除 |
| ⚠️ 部分 | 已动手但未完全闭环 |
| 🔴 开放 | 尚未处理，后续阶段必须覆盖 |
| 📋 监控 | 已知接受风险，需 runbook/人工关注 |

---

## 总览（按严重度）

| 严重度 | 风险摘要 | 主要阶段 | 状态 |
|--------|----------|----------|------|
| **P0** | store 全量 wipe 不可逆 | 1 | ✅ 已执行（有备份） |
| **P0** | 双轨 SoT（新 access/skills/rules vs 旧 adapters/roles） | 2→3 | ✅ legacy 三目录已 git rm（Phase 6 瘦身） |
| **P0** | OpenCode 三源交付 → phantom 完成 / FSM 卡住 | 3 | ✅ Normalizer + 模拟 E2E + **live dali opencode**（P3-S48） |
| **P1** | `bus.py serve` / scheduler 停服 | 1→3 | ✅ serve + scheduler 75s 验 `store/scheduler.log` intake-bridge/scan |
| **P1** | Windows 路径污染复发（C:/E: U+F03A） | 0→3 | ✅ 已清（需 Phase 5 grep） |
| **P1** | init-store / config 合并 | 1→3 | ✅ workflows/schemas/dispatch 镜像；base.json 仍借旧 store 字段 ⚠️ |
| **P2** | symlink/junction 1920（opencode/openclaw skills） | 持续 | ✅ copy+rmtree + `test_install_skill_cleans_junction_dest` |
| **P2** | 9812/9814 端口与 Dashboard 硬编码 | 3 | ✅ compose/Dockerfile 统一 **9814**（2026-06-26） |
| **P2** | 锁命名空间冲突（task lock vs scan lock） | 3 | ✅ push 短锁 + recover 持锁；`task_lock.py` 文档 |
| **P2** | `--fresh` 误跑清空整个 data_dir | 3 | 📋 监控（P3-S08） |

---

## 本会话发现（2026-06-26 Eve · Phase 3.8 门槛闭环）

> 本 Cursor 会话（workflow registry SoT · init-store 镜像 · Normalizer E2E · compose 9814 · test_helpers）。

| ID | 风险 | 影响 | 建议缓解 | 状态 | 阶段 |
|----|------|------|----------|------|------|
| P3-S46 | **docker-agents/*.sh** 仍硬编码 **9812** | compose/Dockerfile 已 9814，WSL 脚本 health/e2e 仍连错口 | `lib/api-url.sh` + `$MAILBUS_API_PORT` 默认 9814 | ✅ | 3.8→5 |
| P3-S47 | fresh store 无 `leads/order-intake.json` | `validate-order-intake` 报 missing（schema 已有） | init-store seed 空数组 | ✅ | 3.8 |
| P3-S48 | Normalizer E2E **live dali** | 仅模拟不足 | `live-dali-opencode-e2e.py` + `verify-live-dali-e2e.py` | ✅ | 5 |
| P3-S49 | `test_pipeline_step_failover` Win 偶发 PermissionError | `json_write` rename `.tmp` WinError 5 | 重试或单测隔离 | 📋 | 3.8 |
| P3-S50 | Phase 3.8 **门槛已过** | legacy 删/adapters 归档过早 | fallback 移除 + DEPRECATED | ✅ | 3.8→5 |

**Phase 3.8 Eve 已交付**：

- `mail/config/workflows/registry.json`（10 workflows）+ `registry.schema.json`
- `mail/rules/schemas/*.json`（6 项含 order-intake）
- `lib/init_store.py`：`mirror_workflows_to_store` / `mirror_rule_schemas_to_store` / `mirror_dispatch_seed` / `mirror_billing_schemas`
- `tests/test_helpers.py` — config/org SoT seed（不依赖已 wipe 的 store/）
- `tests/test_phase38_opencode_e2e.py` — phantom + normalizer + FSM
- `docker-compose.yml` + `mailbus/Dockerfile` → **9814**；`MAILBUS_API_PORT`
- `_send_task` inbox 带 `step_id`/`pipeline_step`；`task_lock.py` 短锁文档
- `validate-order-intake.py` schema 回退 `mail/rules/schemas/`
- dev store：`bus.py init --fresh --data-dir store` ✅
- pytest 核心 **82 passed**；`validate-workflows.py` 10 workflows OK

---

> 本 Cursor 会话（intake bridge / scheduler jobs / task_lock 接入 / Dashboard continue / runbook）。

| ID | 风险 | 影响 | 建议缓解 | 状态 | 阶段 |
|----|------|------|----------|------|------|
| P3-S38 | task_lock **recover 重入** | recover 持锁时 `_send_task` 二次 acquire 失败，repush 不写工单 | `_send_task` 检测已有 holder 跳过重入 acquire（已修） | ✅ | 3.7 |
| P3-S39 | `store/examples/` 被 `.cursorignore` | 示例无法落盘 store；测试读不到 pursue example | SoT 改 `mail/examples/`；`docs/examples-paths.md` | ✅ | 3.8 |
| P3-S40 | fresh wipe 后 `store/workflows/` 空 | `test_p3_intake` workflows_list / spawn 2 项失败 | init-store 镜像 workflows 或 test fixture 内嵌 | ✅ | 3.8 |
| P3-S41 | `validate-order-intake` 依赖 store schema | fresh store 无 `store/rules/order-intake.schema.json` 时 validator FAIL | init-store 镜像 schema 或 validator 读 `mail/rules/` | ✅ | 3.8 |
| P3-S42 | Docker **9812** vs config **9814** | compose health/Dashboard 端口不一致 | compose/env 统一 api_port；文档 smoke | ✅ | 3.7–5 |
| P3-S43 | file_task_push 双轨**有条件** | 仅 task_id+step_id 同时存在才写 work-orders；缺 step_id 仍 msg-files | pipeline push 必带 step_id；或从 content 解析兜底 | ✅ | 3.6+ |
| P3-S44 | task_lock **push 后立即 release** | 与 plan「单写者贯穿 step 执行」可能不一致；scan 仍可能竞态 | 评估持锁至 step 完成/cancel；或文档接受短锁 | ✅ | 3.7–4 |
| P3-S45 | **Phase 3.8 门槛未过勿进 Phase 5** | legacy 删除/adapters 归档过早会断 runtime fallback | 3.8 门槛已过；Phase 5 legacy 仍待终验 | ⚠️ | 3.8→5 |

**Phase 3.6–3.7 已交付（本会话）**：

- `config/intake/bridge.json` + init_store 聚合；`spawn_rules.load_bridge_config` 读静态+store
- `config/scheduler/jobs.json` 全量 jobs SoT；`config/launch/watchdog.json`；`config/env.template`
- `iteration_engine` → `MAILBUS_ROOT`；`handlers_system` openclaw/compose → `MAILBUS_ROOT`
- `handlers_tasks` Hermes usage → `HERMES_DATA`；`handle_agents` 增 canonical_root/agent_json
- `_send_task` task_lock（recover 重入）；`note_pipeline_verify_failure` → pusher + scanner
- `file_task_push` pipeline 双轨（task_id+step_id）；Dashboard `fsm/continue` + `human-queue/resolve`
- `test_framework_skills` / `validate-agent-layers` → v3 skills；`examples/order-intake.pursue.example.json`
- `docs/runbook-recover-cancel.md`、`docs/runbook-phantom-opencode.md`
- pytest 核心 **67 passed**；`bus.py status` ✅；`bus.py serve` + `/api/status` 200 ✅

**仍开放（Phase 3.8 出门槛）**：P3-S39 examples 路径 · scheduler 长跑日志 · Phase 5 legacy 归档

---

## 本会话发现（2026-06-26 · Phase 3.5）

> 上一 Cursor 会话（Work Order + Delivery Normalizer + task lock + recover CLI）。

| ID | 风险 | 影响 | 建议缓解 | 状态 | 阶段 |
|----|------|------|----------|------|------|
| P3-S28 | Normalizer **未 E2E** 验证 | 真实 dali push 后 phantom 可能仍复发 | Phase 3.8 game-courier / opencode 交互回归 | ✅ | 3.8 |
| P3-S29 | patch 无 msg_id 关联时归一化漏网 | 仅文件名 `msg-*.patch` 或 replies.patch 字段才关联 | 规范 opencode delivery.md；补 inbox 反查 | ⚠️ | 3.5–3.8 |
| P3-S30 | `recover --continue` 仅 CLI | Dashboard 继续按钮未接 `task_recover.recover_continue` | Phase 4 handlers_tasks API | ✅ | 4 |
| P3-S31 | task_lock **未接入 push 主路径** | 并发 scan 仍可能双 push 同 task | pipeline_trigger/_send_task acquire/release | ✅ | 3.7 |
| P3-S32 | `file_task_push` 仍只写 msg-files | 非 pipeline 文件任务无 work-orders 镜像 | 复用 write_pipeline_work_order 或共用 helper | ⚠️ | 3.6+ |
| P3-S33 | self_heal `recover_replies` 与 Normalizer 并行 | 非 pipeline 可能双写/逻辑分叉 | 非 pipeline 统一走 Normalizer 或明确边界 | ⚠️ | 3.8 |
| P3-S34 | `record_step_delivery_failure` 未接 scanner | verify_fail 后不自动计次 failover | pusher/scanner verify 路径调用 | ✅ | 3.7 |
| P3-S35 | dispatch.json / verify.json 仅 init 合并 | runtime 代码可能仍读 mailbus_automation 旧字段 | grep 验收 + verify runner 读新 SoT | ⚠️ | 3.6–3.7 |
| P3-S36 | work-order-template 状态行含 `\|` 备选 | parse_work_order_status 曾误判 pending | 已修 regex；保留单测 | ✅ | 3.5 |
| P3-S37 | `bus.py recover` 子命令 argparse | `recover_action` 为 positional，易与 task-id 混淆 | 文档 + 可选 `--continue` flag | 📋 | 3.8 |

**Phase 3.5 已交付**：

- `lib/pipeline_work_order.py` — work-orders SoT + msg-files 双写 + schema 校验
- `lib/delivery_normalizer.py` — replies/patches → msg-results；hook：`self_heal` + `pipeline_trigger`
- `lib/task_lock.py` — `store/locks/task-{task_id}.json`
- `lib/task_recover.py` + `bus.py recover continue|cancel`
- `config/frameworks/opencode/delivery.json`、`config/pipeline/dispatch.json`、`verify.json`；`role_failover.json` 扩展
- `init_store.load_config_fragments` 聚合 framework_delivery / dispatch / verify
- pytest 14 项新测：`test_work_order_schema`、`test_delivery_normalizer_opencode`、`test_task_lock`、`test_recover_continue`、`test_failover_after_two`
- 回归：Phase 3.1–3.4 共 62 passed（含 3.5 新测）

---

## 本会话发现（2026-06-26 · Phase 3.3–3.4）

> 本 Cursor 会话（sync/compose + 适配层切换）编码/测试中暴露的风险。

| ID | 风险 | 影响 | 建议缓解 | 状态 | 阶段 |
|----|------|------|----------|------|------|
| P3-S18 | Windows **JUNCTION** 型 SKILL.md | opencode/openclaw skills 目录内旧 junction 导致 WinError 1920/22，sync installed=0 | `install_skill_spec` 先 `rmtree(dest_dir)`；Phase 5 清宿主机 junction | ✅ | 3.3 |
| P3-S19 | `test_framework_skills.py` 仍断言 adapters/ 路径 | skills-index 已切 v3 但测试仍查 `mail/adapters/` | 改测 `mail/skills/` 或 skip legacy | ✅ | 3.8 |
| P3-S20 | yige workspace 为 `openclaw_space/a-yige` | Dashboard skill 扫描与 xiaoqi 不同目录；勿假设同 skills 根 | agent.json workspace 为准（已 registry 化） | 📋 | 3.4 |
| P3-S21 | `profile_paths.identity` 指向 `mail/identities/*.md` | override 已写但 identity 文件可能不存在 | 改指向 `mail/skills/roles/overlays/{agent}/SKILL.md` | ✅ | 6 |
| P3-S22 | Claude sync：push_cwd ≠ project_dir | lingyun project_dir=`.mailbus/claude/lingyun`，push_cwd 仍 `E:\ai_tools` | 确认 mailbus_claude default_project_roots 与 agent.json workspace 对齐 | 📋 | 3.4 |
| P3-S23 | `handlers_system.py` 硬编码路径 | openclaw.json、docker-agents 路径仍 `/mnt/e/...` | Phase 3.7 Dashboard registry 全量切 | ✅ | 3.7 |
| P3-S24 | `iteration_engine.py` 硬编码 mail 路径 | assess/plan 命令写死 `/mnt/e/ai_tools/mail` | MAILBUS_ROOT + bus 相对路径 | ✅ | 3.6–5 |
| P3-S25 | `validate-agent-layers.py` 仍查 roles/adapters | 与 v3 skills SoT 不一致，可能误报/漏报 | 改查 `mail/skills/` + access adapter spec | ✅ | 3.8 |
| P3-S26 | Hermes 容器 entrypoint agent 列表硬编码 | 新增 hermes_profile agent 需手改 entrypoint.sh | 从 registry 生成或文档化 | 📋 | 3.8 |
| P3-S27 | `access/hermes/.sync/` 为生成物 | gitignore 已加；fresh clone 需跑 sync-all | start-team.sh / entrypoint 自动 sync | 📋 | 3.8 |

**Phase 3.3–3.4 已缓解**：P3-S14 ✅ rules 镜像；P3-S16 ✅ `.sync`+compose；P2-R08 ✅ semgrep→`config/review/semgrep/`；P2-R09 ✅ external-tools；P3-R07 ✅ compose；P3-S10 ⚠️ override 四 agent；P3-S05 ⚠️ privilege/handlers_tasks 部分；P3-R03 ⚠️ sync 全 registry；pytest 30+ 项绿。

---

## 本会话发现（2026-06-26 · Phase 3.1–3.2）

> 历史记录 — 上一 Cursor 会话。

| ID | 风险 | 影响 | 建议缓解 | 状态 | 阶段 |
|----|------|------|----------|------|------|
| P3-S01 | `agent_registry` 进程内缓存 | 改 agent.json 后不 reload 仍用旧数据 | `clear_agent_registry_cache()` 或重启 serve | 📋 | 3.3 |
| P3-S02 | `resolve_mailbus_path` 根推断 | 非标准 data_dir 可能不用 MAILBUS_ROOT | 统一根 + 单测 | 🔴 | 3.5+ |
| P3-S03 | `framework_skills` import 快照 | archetype 列表不随 registry 刷新 | 函数委托 registry | ✅ | 3.3 |
| P3-S04 | 双 registry 命名 | domain `load_registry` vs `agent_registry` 混淆 | 文档/rename | 📋 | 5 |
| P3-S05 | 路径硬编码残留 | privilege/claude_launch/handlers_system 等 | grep + MAILBUS_ROOT（#8 #28） | ⚠️ | 3.7–5 |
| P3-S06 | 工具 CLI 未统一 MAILBUS_DATA | 大量 mail/tools 仍 WSL/相对 store | mailbus-send/memory-bridge ✅；tools 逐步 DEFAULT_DATA_DIR | ⚠️ | 5 |
| P3-S07 | config_schema 仅部分 v3 | 顶层 mailbus_* 无 schema | 扩展 validate | ⚠️ | 3.5 |
| P3-S08 | `--fresh` 整目录 rmtree | **不可逆**丢 inbox/tasks/results | 二次确认/runbook | 📋 | 4 |
| P3-S09 | base.json 源自旧 store | 非纯 config/ SoT，易漂移 | 拆到 config 各域 json | ⚠️ | 3.5+ |
| P3-S10 | fresh init agent 精简 | 缺 launch/profile_paths | `config/agents/*.override.json` | ⚠️ | 3.4 |
| P3-S11 | init_store↔commands 循环依赖 | 懒 import get_system_message | 抽到 lib/messages | 📋 | refactor |
| P3-S12 | org→store/roles/json 仅 init 镜像 | 运行期 org/store 双轨（#5） | fresh 覆盖或直读 org | ⚠️ | 3.5+ |
| P3-S13 | roster lingyun 字段不齐 | 缺 display/role_types | 补齐 org/json/roster | ⚠️ | org |
| P3-S14 | init 未 sync mail/rules→store/rules | 热更新/rules 镜像断链 | sync-team-rules + init_store | ✅ | 3.3 |
| P3-S15 | serve 停服状态未知 | API/scheduler 可能未跑 | 3.8 smoke 重启 | ⚠️ | 3.8 |
| P3-S16 | Hermes .sync 路径迁移 | compose 仍挂 adapters/.sync | access/hermes/.sync | ✅ | 3.3 |
| P3-S17 | test_bus 语义过时 | init 现默认 13 agents | 更新测试 | ✅ | 3.8 |

**历史已缓解**：P1-R04 ✅；agent_registry/rules_registry ✅；init-store+pytest ✅；utils markers #40 ✅

---

## Phase 0 — 冻结与备份

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P0-R01 | 备份不完整 — 只备 config + roles/json | wipe 后无法恢复 pipeline 历史 | intentional wipe；见 `backup-pre-reorg-2026-06-25/BACKUP-MANIFEST.json` | ✅ |
| P0-R02 | 误删保留资产 | team-memory / hermes-data / `.mailbus/claude` 丢失 | wipe 清单 preserve 栏；Phase 0 只读盘点 | ✅ |
| P0-R03 | 备份后 store 仍被 daemon 写入 | 恢复 config 漂移 | 理想：Phase 1 前停服；实际 Phase 1 遇锁才停 | ⚠️ |

**残留**：无 tasks/msg-results 级备份 — 按设计接受。

---

## Phase 1 — 清理 + Fresh Init

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P1-R01 | `mail/store/` 全量 wipe 不可逆 | 3000+ 运行时文件丢失 | Phase 0 备份 config/roster；等你确认 wipe | ✅ |
| P1-R02 | 文件锁导致 store 删不干净 | deliverables 残留 | 停 serve + game.main 后强删 | ✅ |
| P1-R03 | Unicode 污染目录（U+F03A） | PowerShell 误删/漏删 | Python `os.listdir` 精确删除 | ✅ |
| P1-R04 | `init-store --fresh` 不存在 | 手动 fresh init 与 plan 偏差 | `bus.py init --fresh`、`tools/init-store.py` | ✅ |
| P1-R05 | `bus.py serve` 被停 | API 9814 不可用 | 75s + **≥32min** scheduler 长跑 `store/scheduler.log` intake-bridge/scan ✅ | ✅ |
| P1-R06 | game-courier 进程被停 | 进行中任务中断 | live dali `p5-dali-live-*` + game-courier re-submit ✅ | ✅ |
| P1-R07 | 根目录 `E:\ai_tools\store` 复发 | 双 store、patch 路径乱 | 已删；Phase 5 grep（§十 #20） | ✅ |
| P1-R08 | store/rules 内规范随 wipe 丢失 | agent 引用的 task-fsm 等断链 | `mail/rules/` SoT + init/sync 镜像 | ✅ |

**残留**：fresh store 无历史任务；search.db / scheduler 大日志 已清。

---

## Phase 2 — 目录迁移

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P2-R01 | 双轨并存 | 新 SoT 与 adapters/roles/identities 并存 | `adapters/roles/identities/DEPRECATED.md`；runtime 只读 skills/access | ✅ |
| P2-R02 | 代码仍读旧路径 | Phase 2 对 runtime 零生效 | `agent_registry`/`framework_skills` 移除 fallback ✅ | ✅ |
| P2-R03 | hermes_profile 缺 delivery.md | 6 agent rules 引用缺失 | 从 adapters/hermes 补 | ✅ |
| P2-R04 | 扁平 vs 树形 rules 混淆 | 改错文件 | 旧扁平 md 已删；`rules/README.md` | ✅ |
| P2-R05 | `.cursorignore` ignore rules/ | IDE 看不到 SoT | 改为只 ignore `mail/store/` | ✅ |
| P2-R06 | ORGANIZATION.md 双份 | 路径引用不一致 | org/ 已更新；Phase 3 文档合并 | ⚠️ |
| P2-R07 | config/ 仅为 stub | failover/LLM 未进 runtime | init-store 合并 + base.json（P3-S09） | ⚠️ |
| P2-R08 | semgrep 代码路径未切 | review 读旧目录 | `config/review/semgrep/`（#35） | ✅ |
| P2-R09 | external-tools compose 挂载 | 容器仍挂旧路径 | `access/external-tools/`（#34） | ✅ |
| P2-R10 | 复制非移动 adapters/roles | 双倍磁盘；改 skills 漏同步 | DEPRECATED 标记；git 保留历史；禁止 runtime SoT | ✅ |

**残留**：`adapters/.sync/` 可删（已迁 `access/hermes/.sync`）；根目录 `ORGANIZATION.md` 仍在。

---

## Phase 3 — 代码适配

### 3.1 注册表与路径 ✅（2026-06-26）

- 已交付：`agent_registry.py`、`rules_registry.py`、`MAILBUS_ROOT`/`MAILBUS_DATA`、`CONTAINER_STORE_MARKERS`、pytest 18 项
- 残留：P3-S01–S07；sync 仍读 adapters（P3-R03 ⚠️）；路径 grep（P3-S05/S06）

### 3.2 init-store + config ✅（2026-06-26）

- 已交付：`lib/init_store.py`、`bus.py init --fresh`、`tools/init-store.py`、`config/mailbus/base.json`、`test_init_store.py`
- 残留：P3-S08–S14；P3-R08/P3-R16 ⚠️

### 3.3 Sync + Docker ✅（2026-06-26）

- 已交付：`lib/sync_layers.py`、`sync-all-agent-layers.py`、`patch-skills-index-framework.py`、`generate-compose-volumes.py`、`docker-compose.yml` v3、rules 镜像、junction 修复
- pytest：`test_sync_layers.py`；sync smoke 9×5 skills
- 残留：P3-S18–S20、S26–S27

### 3.4 适配层切换 ✅（2026-06-26）

- 已交付：`access_adapters.py`、`agentmemory_config.py`、`privilege.py`、`handlers_tasks` registry、`config/agents/*.override.json`、init-store launch
- pytest：`test_phase34_adapters.py`
- 残留：P3-S21–S25、handlers_system 硬编码

### 3.5 Work Order + Normalizer + FSM ✅（2026-06-26）

- 已交付：见上节 P3-S28–S37「已交付」清单
- 残留：P3-S28–S31、S34–S35；P3-R01/R02 ⚠️；E2E 未跑

### 3.6 intake / human_queue / scheduler ✅（2026-06-26）

- 已交付：`config/intake/bridge.json`、`config/scheduler/jobs.json`、`config/launch/watchdog.json`、`config/env.template`；`iteration_engine` MAILBUS_ROOT；见 P3-S38–S45
- 残留：P3-S40/S41 store 镜像；P3-S43 双轨有条件

### 3.7 端口 / Dashboard / 锁 / failover ✅（2026-06-26）

- 已交付：api_port base.json；handlers_system/tasks 路径；task_lock push；note_pipeline_verify_failure；Dashboard continue/human-queue resolve
- 残留：P3-S42 9812/9814；P3-S44 lock 语义；handlers_tasks 部分路径（P3-S05）

### 3.8 测试 + smoke ⚠️（门槛未过 — 勿进 Phase 4 全量 / Phase 5 legacy 删）

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P3-R01 | Delivery Normalizer | OpenCode phantom done | Normalizer + 模拟 E2E + **live dali** `step-s1.json` ✅ | ✅ |
| P3-R02 | Work Order vs msg-files 双轨 | push 上下文不一致 | work-orders SoT + 双写 ✅（P3-S43） | ✅ |
| P3-R03 | agent_registry 切换遗漏 | validate 误报 | sync/index ✅；validate-agent-layers ✅ | ✅ |
| P3-R04 | 硬编码 `/mnt/e/ai_tools/mail` | WSL/Win/容器不一致 | iteration_engine ✅；**mail/tools CLI 🔴 P3-S06** | ⚠️ |
| P3-R05 | 9812/9814 端口分裂 | health/Dashboard 连错 | compose/Dockerfile + docker-agents `lib/api-url.sh` ✅ | ✅ |
| P3-R06 | Dashboard 硬编码 workspace | 操作写错目录 | handlers_system ✅；handlers_tasks HERMES_DATA ⚠️ | ⚠️ |
| P3-R07 | compose 仍挂旧 adapters | 容器内无新 skills/rules | generate-compose-volumes ✅ | ✅ |
| P3-R08 | init-store 合并出错 | config 与 roster 漂移 | 单测 ✅；base.json 借旧 store（P3-S09） | ⚠️ |
| P3-R09 | task lock vs file lock 冲突 | 死锁/双 push | push/recover ✅；短锁文档 P3-S44 ✅ | ✅ |
| P3-R10 | failover×2 vs RR 冲突 | 异工种改派 | scanner/pusher 计次 ✅ | ✅ |
| P3-R11 | scheduler jobs 硬编码 | 漏 intake-bridge 等 | jobs.json SoT ✅ | ✅ |
| P3-R12 | human_queue 未接 UI | 只能手改 JSON | GET + resolve POST ✅；卡片 UI 待做 | ⚠️ |
| P3-R13 | auto_ack 误当 done | FSM 未验 msg-results | pipeline 禁止 auto done；**live dali verify** msg-results 门禁 ✅ | ✅ |
| P3-R14 | privilege/secrets 路径 | 权限读错根 | privilege.py ✅ | ⚠️ |
| P3-R15 | WSL watchdog 未迁 | 仍用 DEPRECATED boot | watchdog.json ✅；脚本读配置待接 | ⚠️ |
| P3-R16 | store/roles/json vs org/json | role-flow 双 SoT | init-store 镜像 org（#5） | ⚠️ |
| P3-R17 | iteration/workflow/verify 分散 | deliverables 校验不一致 | verify.json 骨架 ✅；runner 对齐待做 | ⚠️ |
| P3-R18 | Breaking API | intake/A2A 调用方失败 | `docs/api.md` + 兼容层（#15） | ✅ |

**Phase 3.8 验收门槛**（2026-06-26 Eve 更新）：

- pytest 核心 **82 passed** ✅（含 `test_p3_intake` 4/4、`test_phase38_opencode_e2e` 4/4）
- `validate-workflows.py` 10 workflows ✅；`validate-agent-layers --check` ✅
- `bus.py init --fresh` 镜像 workflows/schemas/dispatch ✅
- junction 1920：`test_install_skill_cleans_junction_dest` ✅
- phantom/OpenCode E2E：模拟 ✅（真实 CLI → P3-S48）
- **仍开放**：scheduler 长跑日志 · Phase 5 legacy 归档

---

## Phase 4 — Dashboard + 通知（部分执行）

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P4-R01 | 继续/取消/驳回未接 FSM | 按钮只改 UI | Dashboard 任务卡 continue/cancel/rollback/priority ✅ | ✅ | 4 |
| P4-R02 | human_queue 与 Dashboard 不同步 | 人工与自动 push 冲突 | resolve POST 路由 gate/FSM ✅ | ✅ | 4 |
| P4-R03 | alerter 不触发 interrupted | 任务挂死无人知 | `task_interrupt` + scan + alerter | ✅ | 4 |
| P4-R04 | 加急未进 urgent 队列 | priority 无效 | FSM 高优先级 → urgent scan 间隔 | ✅ | 4 |
| P4-R05 | runbook 缺失 | 值班无法处理 reject | recover/cancel + reject/rollback 值班场景 ✅ | ✅ | 4 |
| P4-R06 | fresh init 缺 launch 块 | Dashboard 启动 agent 失败 | override 四 agent；13 人 registry 够用 | ⚠️ | 4 |

---

## Phase 5 — 验证（部分闭环）

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P5-R01 | postmortem 未回归 | phantom/容器/OpenCode 复发 | `p5-dali-live-20260626-155940` live opencode + deliverable + step-s1.json ✅ | ✅ |
| P5-R02 | 全 repo grep 漏网 | 根 store、C:/E: 复活 | 根 store 已删 ✅；docker-agents WSL `/mnt/e` 脚本保留（容器内路径） | ⚠️ |
| P5-R03 | start-all/桌面批处理旧路径 | 一键启动失败 | mailbus-env.sh + 9814 批处理 ✅ | ✅ |
| P5-R04 | §十 #1–#40 未逐项勾选 | 漏项宣称完成 | **本表已收口**（#41–#46 → Phase 6） | ✅ |
| P5-R05 | 测试 fixture 假设旧目录 | CI 假绿 | conftest MAILBUS_ROOT + tmp_store ✅ | ✅ |
| P5-R09 | scheduler **≥30min 长跑**未验 | 长跑 job 泄漏/锁冲突未发现 | 2026-06-26 15:18–15:50+ `scheduler.log`：234× intake-bridge、76× scan ✅ | ✅ |
| P5-R10 | legacy **fallback 未移除** | 删 adapters 会断 runtime | `agent_registry`/`framework_skills` v3-only；`skills/frameworks/hermes` 补齐 ✅ | ✅ |
| P5-R06 | Git E:/ vs E:/ai_tools | clone 路径不一致 | canonical_root 文档（#19） | 📋 |
| P5-R07 | openclaw matt-skills 双 SoT | mail skills 不生效 | domain 策略（#21） | 📋 |
| P5-R08 | ComfyUI/GPU/n8n 未测 | sidecar 回归空 | 可选 smoke（#39） | 📋 |

---

## Phase 6 — 方案设计治理 + 目录清爽（2026-06-26 首轮交付）

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P6-D01 / #41 | **模糊任务未回子言** | 开发猜需求、返工 | `decomposition.md` + `clarifications_needed` → human_queue `owner_confirmation`；FSM block | ✅ |
| P6-D02 / #42 | **复杂任务未拆子任务** | mega 工单压垮开发 | `subtasks[]` DAG + `apply_subtasks_to_chain`；拓扑序写入 planned_role_types | ✅ |
| P6-D03 / #43 | work-order 无 decomposition 字段 | 设计/开发边界模糊 | 模板 + schema + `lib/decomposition.py` + `config/pipeline/decomposition.json` + apply_submit 门禁 | ✅ |
| P6-C01 / #44 | `mail/tools/` 180+ 冗余 | 新人不知用哪个；维护成本高 | 三批：`_incidents` 22 · `_archive` ~95 · `ops/` 39；**根 30** | ✅ |
| P6-C02 / #45 | mail 根杂项脚本/弃用文档 | 目录臃肿 | `_run_*.sh`×4→`_archive/`；`start-all.sh`→`start-team.sh`；`mailbus-boot.sh` DEPRECATED | ✅ |
| P6-C03 / #46 | 脚本目录未按 §二归类 | tools/scripts/docker-agents 混用 | `_archive/`/`_incidents/` + inventory 对照表；支持脚本 20 条；WSL NAT runbook | ✅ |

**Phase 6 设计纪律（写入 rules/workflow，供灵昭/小七执行）**：

1. **模糊** → 停设计步，回 **子言** 对齐（human_queue / clarifications_needed），不得推开发。
2. **复杂** → 必须拆 **有序子任务**，逐步 push，禁止一股脑推 coding-executor。
3. **删脚本** → 全 repo grep + pytest + start-team smoke 通过后方可删。

---

## 跨阶段结构性风险（plan §1.1）

| 问题域 | 描述 | 阶段 | 状态 |
|--------|------|------|------|
| 多源 SoT | identities/roles/config/manifest 不一致 | 2→3 | ⚠️ agent.json + org/ + init-store |
| 路径污染 | sync 写 mail/C:/E: | 1 清；3–5 防复发 | ✅ |
| Legacy | bus/、旧 hermes、旧 rules | 1–2 | ⚠️ adapters 仍在 |
| AgentMemory 分散 | compose/bridge/env 三处 | access/agentmemory/integration.json ✅；team_memory 仍 env | ⚠️ |
| Symlink/junction 1920 | Windows opencode/openclaw skills | copy+rmtree + 单测 | ✅ |
| 交付分裂 | patch/replies vs msg-results | 3 | ✅ Normalizer + E2E 模拟（P3-S28） |
| 守护进程 | serve 退出 → scan 停 | 1 停；3+ 监控 | ⚠️ |

---

## 保留资产红线（勿 wipe）

见 `mail/wipe-manifest.json` preserve：

- `E:\hermes-data\`（含 team-memory.db）
- AgentMemory Docker volume
- `.mailbus/claude/`、`opencode/`、`openclaw_space/`
- `.cursor/plans/`、`mail/plans/backup-pre-reorg-2026-06-25/`
- `mail/{skills,rules,access,config,org}/`

---

## 回滚策略（有限）

| 场景 | 能否回滚 | 做法 |
|------|----------|------|
| config/roster 配错 | 部分 | `backup-pre-reorg-2026-06-25/`、`config/agents/*.override.json` |
| store runtime 误 wipe / `--fresh` | **否** | 仅 JSON 可恢复（P3-S08） |
| Phase 2 目录 | 部分 | git revert；旧 adapters 仍在 |
| Phase 3 代码 | 部分 | 旧路径兼容层 |
| 污染复发 | 是 | wipe-manifest + 修 sync 根因 |

---

## §十 checklist ↔ 风险映射

| §十 # | 风险 ID | 说明 |
|-------|---------|------|
| #5 | P3-R16, P3-S12 | role-flow / org 双轨 |
| #20 | P1-R07 | 根 store 重复 |
| #3 | P3-R02, P3-S32 | work-orders SoT + msg-files 双轨 |
| #4 | P3-R10, P3-S34 | failover×2 |
| #9 | P3-R17, P3-S35 | deliverables/verify |
| #13 | P3-R13 | auto_ack≠done |
| #16 | P3-R09, P3-S31 | task lock |
| #25 | P3-R01, P3-S28 | Normalizer 三源 |
| #11 | P3-S21 | agentmemory integration |
| #12 | P2-R08 | semgrep ✅ |
| #17 | P3-R07 | compose ✅ |
| #27 | P2-R01, P3-S16 | adapters/.sync ✅ |
| #28 | P3-R04, P3-S05, P3-S06 | MAILBUS_ROOT 部分 |
| #34 | P2-R09 | external-tools ✅ |
| #35 | P2-R08 | semgrep ✅ |
| #37 | P3-S21 | agentmemory pending |
| #31 | P1-R03 | C:/E: 污染 |
| #33 | P3-R12, P4-R02 | human_queue |
| #1 | P3-R05, P3-S42 | api_port 9814 文档+脚本 ✅ |
| #36 | — | env.template + mailbus-env.sh ✅ |
| #30 | P5-R03 | start-all/批处理 ✅ |
| #18 | P5-R05 | MAILBUS_ROOT fixture ✅ |
| P3-S38–S45 | 本会话 | 见 §「Phase 3.6–3.8 部分」 |
| #40 | P3-R04 | utils markers ✅ |
| #41–#43 | P6-D01–D03 | 方案设计治理 |
| #44–#46 | P6-C01–C03 | 冗余清理与脚本归类 |

---

## 待办收口清单（下一会话必读 · 2026-06-26）

> **SoT**：本节 + 上表各 ID。完成一项 → 改 `tools/write_reorg_risks.py` → `python tools/write_reorg_risks.py`。  
> **上一会话已闭环（勿重复）**：9814 文档/脚本、mailbus-env.sh、runbook reject/rollback、scheduler 75s、conftest、config/mailbus.json ports、runbook-wsl-codex、render-codex identity 路径、examples v3 补 env 字段、quickstart 弃用 STANDARD_PROCEDURE。

### 🔴 阻塞终验（按顺序）— **Phase 5 已闭环 2026-06-26**

| 序 | ID | 任务 | 验收 | 状态 |
|----|-----|------|------|------|
| 1 | **P3-S48 / P5-R01 / #23** | live dali/opencode：`live-dali-opencode-e2e.py` + `verify-live-dali-e2e.py` | `p5-dali-live-*` step-s1.json + P5_LIVE_OK.txt | ✅ |
| 2 | **P5-R09 / P1-R05** | scheduler ≥30min 长跑 | `scheduler.log` 15:18–15:50+ intake-bridge/scan | ✅ |
| 3 | **P5-R10 / P3-S50** | 移除 legacy fallback | `lib/` grep 无 adapters/roles SoT | ✅ |
| 4 | **P2-R01 / P2-R02 / P2-R10** | deprecate adapters/roles/identities | `DEPRECATED.md` ×3 | ✅ |
| 5 | **P5-R04** | §十 #1–#40 勾选 | 下表 | ✅ |

### 🟠 Phase 6 — 方案设计 + 目录清爽（Phase 5 后可并行，见 plan §六 Phase 6 · #41–#46）

| 序 | ID | 任务 | 验收 | 状态 |
|----|-----|------|------|------|
| 6 | **P6-D01 / #41** | 模糊任务 → 回子言 | `decomposition.md` + owner_confirmation human_queue | ✅ |
| 7 | **P6-D02 / #42** | 复杂任务 subtasks DAG | schema + topo sort + planned_role_types | ✅ |
| 8 | **P6-D03 / #43** | FSM 接 decomposition | `lib/decomposition.py` + apply_submit + 6 pytest | ✅ |
| 9 | **P6-C01 / #44** | tools 盘点归档 | 根 **30**；`ops/` 39；pytest 绿 | ✅ |
| 10 | **P6-C02 / #45** | mail 根杂项 | `start-all.sh`→`start-team.sh` | ✅ |
| 11 | **P6-C03 / #46** | 脚本归类 | inventory + runbook WSL NAT | ✅ |

**清理原则**：删/移任何脚本前 **grep 全 repo + pytest + start-team smoke**；runtime/cron/scheduler 引用的一律保留或改指向。

### ⚠️ 部分完成（顺手关）

| ID | 任务 | 备注 |
|----|------|------|
| P3-S06 / #28 | `mail/tools/*.py` 默认 `DEFAULT_DATA_DIR` | mailbus-send/memory-bridge ✅；grep `MAILBUS_DATA.*store` 余量 |
| P5-R02 | 全 repo grep | `/mnt/e/ai_tools/mail`、`mail/C:`、`mail/E:`、根 store；docker-agents 脚本列清单（WSL 容器内可保留） |
| P3-S05 / #8 | handlers_tasks 路径 → agent.json + canonical_root | privilege ✅ |
| P3-S02 | `resolve_mailbus_path` + MAILBUS_ROOT 单测 | |
| P3-S07 | config_schema 覆盖 mailbus_* | |
| P3-S09 | base.json 拆到 config 各域 | |
| P3-S10 / P4-R06 / #14 | fresh init 13 agent launch 块 | override 仅四 agent；Dashboard 启动验收 |
| P3-S12 / P3-R16 / #5 | org vs store/roles/json 双轨 | 文档接受镜像或运行期直读 org |
| P3-S13 | roster lingyun 字段 | org/json/roster |
| P3-S15 | serve 停服监控 | 健康检查 / systemd 文档 |
| P3-S21 | identity 路径 | access overlay 或补 identities |
| P3-S29 | Normalizer patch 无 msg_id | delivery.md + inbox 反查 |
| P3-S32 | 非 pipeline file_task_push → work-orders | 共用 write_pipeline_work_order |
| P3-S33 | self_heal vs Normalizer 边界 | 文档或统一入口 |
| P3-S35 / P3-R17 / #9 #13 | verify/dispatch runtime 读新 SoT | verify runner 对齐 deliverables |
| P3-R03 | sync adapters fallback | grep 后移除或 deprecated 标记 |
| P3-R12 | human_queue UI | resolve ✅；任务卡/审批 Tab 联调 |
| P3-R13 / #13 | auto_ack ≠ done | pipeline live E2E 验 msg-results 门禁 | ✅ |
| P3-R15 / #29 | watchdog 脚本读 watchdog.json | mailbus-launch-watchdog.sh |
| P3-R06 / #2 #6 | Dashboard handlers_tasks 硬编码 | agent.json 解析 workspace |
| P1-R06 | game-courier 进程 | 随 P5-R01 live E2E 一并验 | ✅ |

### 📋 观察项（可文档化，不阻塞）

P3-S01 · P3-S04 · P3-S08 · P3-S11 · P3-S20 · P3-S22 · P3-S26 · P3-S27 · P3-S37 · P3-S49 · P5-R06/#19 · P5-R07/#21 · P5-R08/#39 · P2-R06 · P2-R07 · P0-R03

### §十 #1–#40 终验表（P5-R04）

| # | 项 | 状态 |
|---|-----|------|
| 1 | API 9814 统一 | ✅ |
| 2 | Dashboard → agent.json | ⚠️ handlers_tasks |
| 3 | work-orders SoT | ✅ |
| 4 | dispatch + role_failover | ✅ |
| 5 | org vs store/roles/json | ⚠️ |
| 6 | Docker generate-compose-volumes | ⚠️ |
| 7 | .cursorignore mail/rules | ✅ |
| 8 | privilege MAILBUS_ROOT | ⚠️ P3-S05 |
| 9 | Iteration Engine | ⚠️ |
| 10 | Workflow + human_queue | ✅ |
| 11 | team-memory.db integration | ⚠️ env |
| 12 | n8n/Dify/semgrep | ✅ semgrep |
| 13 | Tracker / verify escalation | ✅ live dali gate |
| 14 | Agent launch 块 | ⚠️ 四 agent override |
| 15 | docs/api.md | ✅ |
| 16 | 锁命名空间 | ✅ |
| 17 | compose mail/rules SoT | ✅ |
| 18 | MAILBUS_ROOT fixture | ✅ |
| 19 | canonical_root 文档 | 📋 |
| 20 | 根 store + grep | ✅ |
| 21 | matt-skills 双 SoT | 📋 |
| 22 | board/sent wipe | ✅ |
| 23 | game-courier live E2E | ✅ `p5-dali-live-*` + postmortem 2026-06-25 |
| 24 | workspace 迁入 access | Phase 6 |
| 25 | Normalizer 三源 | ✅ 模拟 + live |
| 26 | deliverables 契约 | ✅ |
| 27 | adapters/.sync | ✅ |
| 28 | CLI MAILBUS_DATA | ⚠️ P3-S06 |
| 29 | watchdog.json | ⚠️ P3-R15 |
| 30 | start-all/批处理 | ✅ |
| 31 | 污染 mail/E: | ✅ |
| 32 | intake bridge | ✅ |
| 33 | human-queue Dashboard | ✅ |
| 34 | external-tools | ✅ |
| 35 | semgrep config/review | ✅ |
| 36 | env.template 链 | ✅ mailbus-env.sh |
| 37 | agentmemory-pending | ✅ |
| 38 | scheduler jobs.json | ✅ |
| 39 | ComfyUI/GPU/n8n | 📋 |
| 40 | utils path markers | ✅ |
| 41 | 模糊任务回子言 | ✅ P6-D01 |
| 42 | 复杂任务拆 subtasks | ✅ P6-D02 |
| 43 | decomposition 契约 | ✅ P6-D03 |
| 44 | tools 冗余清理 | ✅ 根 30 + ops/39 + archive |
| 45 | mail 根杂项清理 | ✅ start-all→start-team |
| 46 | 脚本目录归类 | ✅ inventory + runbook |

### §10.7 杂项

| 项 | 状态 |
|----|------|
| examples/config.example.json v3 | ✅ 补 mailbus_data_env |
| STANDARD_PROCEDURE → quickstart | ✅ 指针 |
| docs/runbook-wsl-codex.md | ✅ |
| config/mailbus.json ports | ✅ |
| render-codex-config.sh 路径 | ✅ access 优先 |

### 建议执行顺序（风险登记驱动）

1. 读本文件 §「待办收口清单」+ §十表  
2. **P5-R01** live E2E（Docker）  
3. **P5-R09** scheduler 30min  
4. **P5-R02 + P3-S06** grep 收尾  
5. **P5-R10 → P2-R01** legacy fallback 移除 + deprecate  
6. **C 组**开放风险按 grep 结果关项  
7. **P5-R04** §十表逐项改 ✅  
8. `write_reorg_risks.py` → `python tools/write_reorg_risks.py`

### 关键命令

```bash
cd E:/ai_tools/mail
python tools/write_reorg_risks.py                    # 风险写回
python -m pytest tests/test_phase4_dashboard.py tests/test_phase38_opencode_e2e.py tests/test_init_store.py -v
python bus.py init --fresh --data-dir store          # 仅 dev
# live E2E（WSL）
cd docker-agents && bash start-team.sh
bash submit-game-courier-task.sh && bash mailbus-pipeline-e2e.sh
# grep
rg "/mnt/e/ai_tools/mail" --glob "!*.md" --glob "!write_reorg*"
rg "9812" mail/docker-agents mail/tools mail/scripts scripts
Test-Path E:/ai_tools/store   # 应为 False
```

---

## 变更记录

| 日期 | 内容 |
|------|------|
| 2026-06-26 AM | 初版：Phase 0–2 执行风险 + plan §10 推导 Phase 3–5 |
| 2026-06-26 PM | Phase 3.1–3.2；P3-S01–S17 |
| 2026-06-26 Eve | **Phase 3.3–3.4**；新增 P3-S18–S27；更新 compose/semgrep/agentmemory/launch 状态 |
| 2026-06-26 Late | **Phase 3.5**；Work Order/Normalizer/task_lock/recover；新增 P3-S28–S37；62 pytest passed |
| 2026-06-26 Eve | **Phase 3.8 门槛闭环**；workflow registry SoT + init-store 镜像；82 pytest；P3-S46–S50；compose 9814 |
| 2026-06-26 Night | **Phase 3.6–3.7** + 3.8 部分；新增 P3-S38–S45；67 pytest；serve smoke 200；Dashboard continue/human-queue resolve；runbook 2 篇 |
| 2026-06-26 Final | **Phase 4 收尾 + Phase 5 部分**：9814 文档/脚本、mailbus-env.sh、runbook reject/rollback、scheduler.log 验 intake-bridge、conftest MAILBUS_ROOT、config/mailbus.json ports |
| 2026-06-26 Handoff | **待办收口清单**入风险登记；新增 P5-R09/P5-R10；handoff → `docs/handoff-risks-closure.md` |
| 2026-06-26 + | **Phase 6** 入 plan §六/§9.10/§10.8–10.9；P6-D01–D03 设计治理 + P6-C01–C03 冗余/脚本归类 |
| 2026-06-26 Phase5 | **Phase 5 终验**：live dali opencode、scheduler 32min、legacy fallback 移除、DEPRECATED ×3 |
| 2026-06-26 P6-slim | **Phase 6 瘦身**：legacy 三目录 git rm · 污染 C/E 删 · 根杂项→`_archive/` · `config/` 重建 · pytest 56 passed |
'''

def main() -> None:
    out = Path(__file__).resolve().parent.parent / "docs" / "reorg-risks-by-phase.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(CONTENT.lstrip("\n"), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
