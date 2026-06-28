# Mailbus 架构重组 — 风险登记收口 Handoff

> **用途**：新会话专读风险登记、逐项闭环剩余待办。  
> **SoT**：`mail/plans/reorg-risks-by-phase.md`（由 `python mail/tools/write_reorg_risks.py` 生成）  
> **计划**：`C:\Users\hopew\.cursor\plans\mailbus_架构重组_bbc0d4a3.plan.md`（含 §六 Phase 6、§9.10–9.11、§10.8–10.9 #41–#46）  
> **wipe**：`mail/wipe-manifest.json`

---

## 提示词块（复制整段到新对话）

```
# 任务：Mailbus 架构重组 — 风险登记收口（Phase 5 终验 + Phase 6 设计/清理）

工作区：`E:\ai_tools`
**唯一待办 SoT**：`E:\ai_tools\mail\plans\reorg-risks-by-phase.md`
  → 必读 §「待办收口清单」+ §十 #1–#46 终验表 + Phase 6 表
计划 SoT：`C:\Users\hopew\.cursor\plans\mailbus_架构重组_bbc0d4a3.plan.md`（§二目录模型 · §六 Phase 6 · §9.10 设计治理 · §10.8–10.9）
写回：`mail/tools/write_reorg_risks.py` → `python mail/tools/write_reorg_risks.py`

---

## 硬约束

- 可 wipe：`mail/store/`、`mail/logs/`、污染目录、`E:\ai_tools\store/`、`adapters/.sync`
- **禁止**对生产 store 跑 `--fresh`（P3-S08）
- **禁止**在 P5-R10 完成前删/归档 `mail/adapters/`、`mail/roles/`、`mail/identities/` → **已闭环**（Phase 6 瘦身已 git rm）
- **删/移任何脚本前**：全 repo grep 引用 + pytest + start-team smoke
- 不擅自 git commit/push
- 每闭环一项：更新 `write_reorg_risks.py` → 跑 write 脚本

---

## 方案设计阶段纪律（Phase 6 · 灵昭/小七 · #41–#43）

> 已写入 plan §9.10、§10.8；风险 ID：**P6-D01 / P6-D02 / P6-D03**

1. **任务模糊**（Intent / Scope / Acceptance 任一不清或矛盾）
   - **必须**停在方案设计 step，写 `clarifications_needed` 或 human_queue「待主人确认」
   - **回子言商量对策**，对齐后再拆单 — **禁止**直接 push 开发让编码 agent 猜需求

2. **任务复杂**（跨模块、多工种、多个可独立验收增量）
   - 方案阶段 **必须**产出有序 **subtasks[] DAG**（依赖、assignee/role、验收点）
   - FSM **按子任务逐步** push — **禁止**一个 mega 工单一股脑推给 coding-executor（大力/灵云）

3. **待设计/开发落盘**（本阶段任务，非仅文档）
   - `mail/rules/roles/spec-designer/decomposition.md`（或等价 rules）
   - work-order 模板增 Subtasks / Clarifications 段 + schema
   - workflow gate `require_decomposition`；Dashboard「待主人确认」Tab

---

## 冗余清理 + 目录清爽（Phase 6 · #44–#46）

> plan §9.11、§10.9；风险 ID：**P6-C01 / P6-C02 / P6-C03**

**现状问题**：`mail/tools/` 180+ 文件，大量 `patch-*`/`debug-*`/一次性脚本；根目录 `_run_*.sh`、`mailbus-boot.sh`（DEPRECATED）；`mail/scripts/` 与 `tools/`、`docker-agents/`、repo 根 `scripts/` 混用。

**目标**（对照 plan §二目录模型）：

| 位置 | 应放什么 |
|------|----------|
| `mail/lib/` | 运行时总线逻辑 |
| `mail/tools/` | sync · validate · init · 验收 · 运维（支持表 **≤20**） |
| `mail/tools/_archive/` | 无引用历史脚本 |
| `mail/tools/_incidents/` | postmortem 一次性脚本 |
| `mail/docker-agents/` | 容器 compose + 团队启动/health/e2e |
| `E:\ai_tools\scripts/` + 桌面批处理 | WSL/Windows 入口（读 mailbus-env.sh） |
| `mail/scripts/` | 极简，仅 mailbus 容器运维必要项 |

**执行步骤**：
1. 盘点 → `docs/tools-inventory.md`（保留/归档/删除 + grep 证据）
2. 无 runtime/cron/scheduler/CI 引用 → 移 `_archive/` 或删
3. mail 根杂项（`_run_git_ops*.sh`、弃用 STANDARD_PROCEDURE 等）grep 后清
4. quickstart/README 只列支持脚本表

---

## 已完成（勿重复）

Phase 0–4 ✅ · 9814/docs/scripts ✅ · mailbus-env.sh ✅ · runbook 全套 ✅ · scheduler 75s ✅ · conftest ✅ · config/mailbus.json ✅ · 根 store 不存在 ✅

---

## 待做（按风险登记 §「待办收口清单」顺序）

### 🔴 Phase 5 阻塞（按序 1–5）

1. P3-S48 / P5-R01 / #23 — live Docker E2E
2. P5-R09 — scheduler ≥30min
3. P5-R10 — legacy fallback 移除
4. P2-R01 — deprecate adapters/roles/identities
5. P5-R04 — §十 #1–#40 勾选

### 🟠 Phase 6（6–11，可与 5 并行规划，清理建议在 5 终验后大动）

6. P6-D01 / #41 — 模糊任务回子言（**待设计**）
7. P6-D02 / #42 — 复杂任务 subtasks DAG（**待设计**）
8. P6-D03 / #43 — work-order/FSM decomposition（**待开发**）
9. P6-C01 / #44 — tools/ 冗余盘点归档（**待开发**）
10. P6-C02 / #45 — mail 根杂项清理（**待开发**）
11. P6-C03 / #46 — 脚本目录归类（**待开发**）

### ⚠️ 部分完成 · 📋 观察

见风险登记 §「待办收口清单」对应表

---

## 关键路径

| 用途 | 路径 |
|------|------|
| 风险登记 | `mail/plans/reorg-risks-by-phase.md` |
| 重组计划 | `C:\Users\hopew\.cursor\plans\mailbus_架构重组_bbc0d4a3.plan.md` |
| 目标目录模型 | plan §二 |
| live E2E | `mail/docker-agents/submit-game-courier-task.sh` |
| legacy grep | `mail/lib/agent_registry.py`、`framework_skills.py` |
| tools 盘点（待建） | `mail/docs/tools-inventory.md` |

## 验收命令

```bash
cd E:/ai_tools/mail
python tools/write_reorg_risks.py
python -m pytest tests/test_phase4_dashboard.py tests/test_phase38_opencode_e2e.py tests/test_init_store.py -v
# 删脚本前必跑
rg "script_name" --glob "!*.md"
# tools 盘点
Get-ChildItem mail/tools -File | Measure-Object
```

## 汇报格式

**做了什么 / 测了什么 / 关了哪些风险 ID / §十 # 勾选 / 删了哪些脚本（附 grep 证据）**
```

---

## 变更记录

| 日期 | 内容 |
|------|------|
| 2026-06-26 | 初版：Phase 5 收口 handoff |
| 2026-06-26 + | 增 Phase 6 设计治理 + 冗余/脚本归类；plan #41–#46 |
