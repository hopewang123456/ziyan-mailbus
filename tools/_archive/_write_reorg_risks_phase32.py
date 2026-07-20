#!/usr/bin/env python3
"""Write mail/plans/reorg-risks-by-phase.md — Phase 3.1/3.2 session update."""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "plans" / "reorg-risks-by-phase.md"

CONTENT = """# Mailbus 架构重组 — 分阶段风险登记

> 计划 SoT：`C:\\Users\\hopew\\.cursor\\plans\\mailbus_架构重组_bbc0d4a3.plan.md`  
> 更新：2026-06-26 · Phase 0–2 已执行；**Phase 3.1–3.2 已执行**；Phase 3.3–5 待执行  
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
| **P0** | 双轨 SoT（新 access/skills/rules vs 旧 adapters/roles） | 2→3 | 🔴 开放 |
| **P0** | OpenCode 三源交付 → phantom 完成 / FSM 卡住 | 3 | 🔴 开放 |
| **P0** | `init --fresh` 无确认即 rmtree 整个 data_dir | 3.2 | 🔴 开放 |
| **P1** | `bus.py serve` / scheduler 停服 | 1→3 | ⚠️ 部分 |
| **P1** | Windows 路径污染复发（C:/E: U+F03A） | 0→3 | ✅ 已清（需 Phase 5 grep） |
| **P1** | init-store / config 合并 | 3.2 | ⚠️ 部分 |
| **P2** | symlink error 1920（opencode/openclaw skills） | 持续 | 📋 监控 |
| **P2** | 9812/9814 端口与 Dashboard 硬编码 | 3 | 🔴 开放 |
| **P2** | 锁命名空间冲突（task lock vs scan lock） | 3 | 🔴 开放 |
| **P2** | fresh init agent 配置缺 launch/identity | 3.2 | 🔴 开放 |

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
| P1-R04 | `init-store --fresh` 不存在 | 手动 fresh init 与 plan 偏差 | **已实现**：`bus.py init --fresh`、`tools/init-store.py --fresh` | ✅ |
| P1-R05 | `bus.py serve` 被停 | API 9814 不可用 | Phase 3/5 重启 | ⚠️ |
| P1-R06 | game-courier 进程被停 | 进行中任务中断 | Phase 5 postmortem | ⚠️ |
| P1-R07 | 根目录 `E:\\ai_tools\\store` 复发 | 双 store、patch 路径乱 | 已删；Phase 5 grep（§十 #20） | ✅ |
| P1-R08 | store/rules 内规范随 wipe 丢失 | agent 引用的 task-fsm 等断链 | Phase 2 在 `mail/rules/common/` 重建 | ✅ |

**残留**：fresh store 无历史任务；search.db / scheduler 大日志 已清。

---

## Phase 2 — 目录迁移

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P2-R01 | 双轨并存 | 新 SoT 与 adapters/roles/identities 并存 | Phase 3 切 registry；Phase 5 grep | 🔴 |
| P2-R02 | 代码仍读旧路径 | Phase 2 对 runtime 零生效 | 预期；勿误以为可上线 | 📋 |
| P2-R03 | hermes_profile 缺 delivery.md | 6 agent rules 引用缺失 | 从 adapters/hermes 补 | ✅ |
| P2-R04 | 扁平 vs 树形 rules 混淆 | 改错文件 | 旧扁平 md 已删；`rules/README.md` | ✅ |
| P2-R05 | `.cursorignore` ignore rules/ | IDE 看不到 SoT | 改为只 ignore `mail/store/` | ✅ |
| P2-R06 | ORGANIZATION.md 双份 | 路径引用不一致 | org/ 已更新；Phase 3 文档合并 | ⚠️ |
| P2-R07 | config/ 仅为 stub | failover/LLM 未进 runtime | init-store 合并 fragment；base.json 仍非纯手写 SoT | ⚠️ |
| P2-R08 | semgrep 代码路径未切 | review 读旧目录 | Phase 3 → `config/review/semgrep/`（#35） | 🔴 |
| P2-R09 | external-tools compose 挂载 | 容器仍挂旧路径 | Phase 3 compose（#34） | 🔴 |
| P2-R10 | 复制非移动 adapters/roles | 双倍磁盘；改 skills 漏同步 | Phase 3 后 deprecate 旧树 | 📋 |

**残留**：`adapters/.sync/` 仍写旧路径（#27）；根目录 `ORGANIZATION.md` 仍在。

---

## Phase 3.1 — 注册表与路径（2026-06-26 会话）

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P3.1-R01 | `framework_skills.AGENT_ARCHETYPES` 模块 import 时缓存 | 改 agent.json 后 sync 脚本仍用旧 archetype | 调用 `clear_agent_registry_cache()`；Phase 3.3 sync 改读 registry 实时扫描 | ⚠️ |
| P3.1-R02 | `resolve_mailbus_path` 非标准 layout | data_dir 不在 `mail/store` 时 root 解析错误 | 已优先 `MAILBUS_ROOT`（有 access/ 时）；边缘 layout 仍可能错 | ⚠️ |
| P3.1-R03 | 大量代码仍硬编码 `/mnt/e/ai_tools/mail` | WSL/Win/容器路径不一致 | constants 已收口；`privilege.py`、`claude_launch.py`、`handlers_tasks.py` 待 Phase 3.5/5 grep（#8、#28） | 🔴 |
| P3.1-R04 | `agent_registry` 与 `load_registry(data_dir)` 同名概念 | 新人混淆 domain registry vs access registry | 文档区分；Phase 5 考虑重命名 domain registry | 📋 |
| P3.1-R05 | Hermes sync 目标改为 `access/hermes/.sync/` | compose 仍挂 `adapters/.sync` 则容器看不到 skills | Phase 3.3 compose + generate-compose-volumes（#27） | 🔴 |
| P3.1-R06 | `to_container_store_path` markers 扩展 | 仅覆盖 rewrite 路径；push 正文仍可能漏新目录 | Phase 3.5 工单/deliverables push 模板验收 | ⚠️ |

**本步已完成**：`agent_registry.py`、`rules_registry.py`、`MAILBUS_ROOT`/`MAILBUS_DATA`、`CONTAINER_STORE_MARKERS`、pytest 18 项。

---

## Phase 3.2 — init-store + config 合并（2026-06-26 会话）

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P3.2-R01 | **`init --fresh` 直接 `rmtree(data_dir)`** | inbox/tasks/msg-results 全丢，无二次确认 | 加 `--yes` 或交互确认；runbook 强调备份；文档红字 | 🔴 |
| P3.2-R02 | `config/mailbus/base.json` 从旧 store 克隆 | 非模块化 SoT；旧字段长期滞留 | 逐步拆到 `config/{llm,pipeline,mailbus}/`；删 agents 后手写维护 | 🔴 |
| P3.2-R03 | fresh init 的 agent 条目为**精简版** | 缺 `launch`、`profile_paths`、identity 路径 | `config/agents/{id}.override.json` 或 Phase 4 launch 块；对比 Phase 0 备份补全 | 🔴 |
| P3.2-R04 | `org/json` → `store/roles/json` 为**拷贝非 symlink** | 改 org/ 后 store 漂移，FSM 读旧 role-flow | init 后提示 re-run `--fresh`；或 Phase 3.5 watch org mtime | ⚠️ |
| P3.2-R05 | `roster.json` 中 lingyun 条目 schema 不一致 | 缺 `display`/`role_types`；init 回退用 name 字段 | 补齐 roster 与 agent-registry | ⚠️ |
| P3.2-R06 | `init_store` → `commands.get_system_message` 延迟 import | 潜在 circular import | 将 welcome 消息生成下沉到 utils | 📋 |
| P3.2-R07 | **`bus.py init` 行为变更** | 旧行为空 agents + 手动 agent-add；现为 13 agents 全自动 | 文档更新；旧脚本若依赖空 init 会失败 | ⚠️ |
| P3.2-R08 | `config_schema` 仅扩展 agents 字段 | 顶层 `mailbus_*` 键未入 schema | 扩展 CONFIG_SCHEMA 或 relax additionalProperties | ⚠️ |
| P3.2-R09 | init-store 单测用真实 MAILBUS_ROOT | CI/无 access 目录环境失败 | fixture 目录或 Phase 5 MAILBUS_ROOT fixture（#18） | ⚠️ |

**本步已完成**：`lib/init_store.py`、`tools/init-store.py`、`bus.py init --fresh`、org 镜像、runtime 骨架、pytest test_init_store（5 项）。

---

## Phase 3 — 代码适配（剩余待执行）

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P3-R01 | Delivery Normalizer 未落地 | OpenCode phantom done | 三源 → msg-results（#25） | 🔴 |
| P3-R02 | Work Order vs msg-files 双轨 | push 上下文不一致 | work-orders SoT；过渡期兼容（#3） | 🔴 |
| P3-R03 | agent_registry 切换遗漏 | sync 仍读 adapters | 3.1 已建 registry；3.3 sync 待切 | ⚠️ |
| P3-R04 | 硬编码 `/mnt/e/ai_tools/mail` | WSL/Win/容器不一致 | 3.1 constants 已收口；全库 grep 待 Phase 5（#28、#40） | ⚠️ |
| P3-R05 | 9812/9814 端口分裂 | health/Dashboard 连错 | config/mailbus.json（#1） | 🔴 |
| P3-R06 | Dashboard 硬编码 workspace | 操作写错目录 | agent.json + canonical_root（#2） | 🔴 |
| P3-R07 | compose 仍挂旧 adapters | 容器内无新 skills/rules | generate-compose-volumes（#6、#17） | 🔴 |
| P3-R08 | init-store 合并出错 | config 与 roster 漂移 | 3.2 pytest + validate_config；对比 backup 仍待人工 | ⚠️ |
| P3-R09 | task lock vs file lock 冲突 | 死锁/双 push | 命名空间分离（#16） | 🔴 |
| P3-R10 | failover×2 vs RR 冲突 | 异工种改派 | role_failover.json（#4） | 🔴 |
| P3-R11 | scheduler jobs 硬编码 | 漏 intake-bridge 等 | jobs.json SoT 已存在；scheduler 代码待接（#38） | ⚠️ |
| P3-R12 | human_queue 未接 UI | 只能手改 JSON | Phase 3 API；Phase 4 UI（#33） | 🔴 |
| P3-R13 | auto_ack 误当 done | FSM 未验 msg-results | pipeline 禁止 auto done（§9.2） | 🔴 |
| P3-R14 | privilege/secrets 路径 | 权限读错根 | MAILBUS_ROOT（#8） | 🔴 |
| P3-R15 | WSL watchdog 未迁 | 仍用 DEPRECATED boot（#29） | config/launch/watchdog.json | 🔴 |
| P3-R16 | store/roles/json vs org/json | role-flow 双 SoT | init-store 镜像（3.2）；长期需 org 为唯一写源 | ⚠️ |
| P3-R17 | iteration/workflow/verify 分散 | deliverables 校验不一致 | config/pipeline/verify.json（#9、#26） | 🔴 |
| P3-R18 | Breaking API | intake/A2A 调用方失败 | docs/api.md + 兼容层（#15） | 🔴 |

**Phase 3 验收门槛**（未满足勿进 Phase 4）：

- pytest：registry ✅、Normalizer 三源 🔴、container paths ✅、init-store ✅
- `bus.py status` 13 agents ✅；可选 serve smoke ⚠️
- runtime 不再以 adapters/roles 为 SoT（仅兼容层）🔴

**下一步**：Phase 3.3 sync + Docker compose。

---

## Phase 4 — Dashboard + 通知（待执行）

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P4-R01 | 继续/取消/驳回未接 FSM | 按钮只改 UI | apply_cancel / recover / rollback | 🔴 |
| P4-R02 | human_queue 与 Dashboard 不同步 | 人工与自动 push 冲突 | API + 卡片联动 | 🔴 |
| P4-R03 | alerter 不触发 interrupted | 任务挂死无人知 | task lock + alerter + runbook | 🔴 |
| P4-R04 | 加急未进 urgent 队列 | priority 无效 | urgent scan（§9.3） | 🔴 |
| P4-R05 | runbook 缺失 | 值班无法处理 reject | docs/runbook-*.md | 🔴 |
| P4-R06 | fresh init 缺 launch 块 | Dashboard 启动按钮无效 | 补 agent launch + override（承接 P3.2-R03） | 🔴 |

---

## Phase 5 — 验证（待执行）

| ID | 风险 | 影响 | 缓解措施 | 状态 |
|----|------|------|----------|------|
| P5-R01 | postmortem 未回归 | phantom/容器/OpenCode 复发 | game-courier E2E（#23） | 🔴 |
| P5-R02 | 全 repo grep 漏网 | 根 store、C:/E: 复活 | mail + ai_tools grep（#30） | 🔴 |
| P5-R03 | start-all/桌面批处理旧路径 | 一键启动失败 | 更新脚本 + env | 🔴 |
| P5-R04 | §十 #1–#40 未逐项勾选 | 漏项宣称完成 | plan §10 终验 | 🔴 |
| P5-R05 | 测试 fixture 假设旧目录 | CI 假绿 | MAILBUS_ROOT fixture（#18） | 🔴 |
| P5-R06 | Git E:/ vs E:/ai_tools | clone 路径不一致 | canonical_root 文档（#19） | 📋 |
| P5-R07 | openclaw matt-skills 双 SoT | mail skills 不生效 | domain 策略（#21） | 📋 |
| P5-R08 | ComfyUI/GPU/n8n 未测 | sidecar 回归空 | 可选 smoke（#39） | 📋 |
| P5-R09 | `init --fresh` 误跑生产 store | 灾难性数据丢失 | 确认 prompt + runbook + 非 prod 默认 | 🔴 |

---

## 跨阶段结构性风险（plan §1.1）

| 问题域 | 描述 | 阶段 | 状态 |
|--------|------|------|------|
| 多源 SoT | identities/roles/config/manifest 不一致 | 2→3 | ⚠️ → agent.json + org/ + init-store |
| 路径污染 | sync 写 mail/C:/E: | 1 清；3–5 防复发 | ✅ |
| Legacy | bus/、旧 hermes、旧 rules | 1–2 | ⚠️ adapters 仍在 |
| AgentMemory 分散 | compose/bridge/env 三处 | 2 stub；3 统一 | ⚠️ |
| Symlink 1920 | Windows opencode/openclaw skills | 持续 | 📋 copy 默认 |
| 交付分裂 | patch/replies vs msg-results | 3 | 🔴 |
| 守护进程 | serve 退出 → scan 停 | 1 停；3+ 监控 | ⚠️ |
| config 模板债 | base.json 克隆自旧 store | 3.2 | 🔴 需拆域 json |

---

## 保留资产红线（勿 wipe）

见 `mail/wipe-manifest.json` preserve：

- `E:\\hermes-data\\`（含 team-memory.db）
- AgentMemory Docker volume
- `.mailbus/claude/`、`opencode/`、`openclaw_space/`
- `.cursor/plans/`、`mail/plans/backup-pre-reorg-2026-06-25/`
- `mail/{skills,rules,access,config,org}/`

---

## 回滚策略（有限）

| 场景 | 能否回滚 | 做法 |
|------|----------|------|
| config/roster 配错 | 部分 | `backup-pre-reorg-2026-06-25/` |
| store runtime 误 wipe | **否** | 仅 JSON 可恢复；**禁止无确认 `--fresh`** |
| Phase 2 目录 | 部分 | git revert；旧 adapters 仍在 |
| Phase 3 代码 | 部分 | 旧路径兼容层 |
| 污染复发 | 是 | wipe-manifest + 修 sync 根因 |

---

## §十 checklist ↔ 风险映射

| §十 # | 风险 ID | 说明 | 3.1/3.2 进度 |
|-------|---------|------|--------------|
| #5 | P3-R16, P3.2-R04 | role-flow SoT | ⚠️ init 镜像 |
| #8 | P3-R14, P3.1-R03 | privilege MAILBUS_ROOT | 🔴 |
| #20 | P1-R07 | 根 store 重复 | ✅ |
| #25 | P3-R01 | Normalizer 三源 | 🔴 |
| #27 | P2-R01, P3.1-R05 | adapters/.sync | 🔴 |
| #28 | P3-R04, P3.1-R03 | CLI 硬编码 | ⚠️ |
| #31 | P1-R03 | C:/E: 污染 | ✅ |
| #33 | P3-R12, P4-R02 | human_queue | 🔴 |
| #35 | P2-R08 | semgrep 路径 | 🔴 |
| #38 | P3-R11 | scheduler jobs | ⚠️ json 有，代码未接 |
| #40 | P3-R04, P3.1-R06 | utils markers | ✅ |

---

## 变更记录

| 日期 | 内容 |
|------|------|
| 2026-06-26 AM | 初版：Phase 0–2 执行风险 + plan §10 推导 Phase 3–5 |
| 2026-06-26 PM | Phase 3.1–3.2 会话：新增 P3.1-R* / P3.2-R*；更新 P1-R04✅、P3-R03/04/08/16⚠️；总览与验收门槛同步 |
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(CONTENT, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
