# Mailbus 重组 — 下一会话 Handoff

> 复制下方「提示词块」整段到新 Cursor 会话。  
> SoT：`mail/plans/reorg-risks-by-phase.md` · 计划：`C:\Users\hopew\.cursor\plans\mailbus_架构重组_bbc0d4a3.plan.md`

---

## 上一会话已闭环（勿重复）

- Phase 0–5 阻塞终验 ✅
- P6-D01–D03 / #41–#43：decomposition 门禁、`lib/decomposition.py`、6 pytest ✅
- P6-C01 首批：22→`_incidents/`，8→`_archive/`，`docs/tools-inventory.md` ✅
- mail 根 `_run_*.sh`×4 → `tools/_archive/` ✅
- 验收：pytest 57 passed · `verify-live-dali-e2e.py` PASS

---

## 提示词块（复制整段）

```
# 任务：Mailbus 重组收口 — tools 第二批归档 + 环境残留

工作区：`E:\ai_tools`
**SoT**：`E:\ai_tools\mail\plans\reorg-risks-by-phase.md` → §「待办收口清单」+ §十 #1–#46
**盘点**：`E:\ai_tools\mail\docs\tools-inventory.md`
**写回**：`mail/tools/write_reorg_risks.py` → `python mail/tools/write_reorg_risks.py`

---

## 硬约束

- 可 wipe：`mail/store/`、`mail/logs/`、`E:\ai_tools\store/`
- **禁止**对生产 store 跑 `--fresh`（P3-S08）
- **legacy 已删**：`mail/adapters/`、`mail/roles/`、`mail/identities/`（2026-06-26 Phase 6）
- **删/移脚本前**：全 repo `rg` + pytest +（大批量后）start-team smoke
- 不擅自 git commit/push
- 每闭环一项：改 `write_reorg_risks.py` → `python tools/write_reorg_risks.py`

---

## 执行顺序（本会话）

### 🔴 第一优先：P6-C01 第二批 tools 归档（#44）

**现状**：`mail/tools/` 根目录 ~130+ 文件；支持脚本 20 条已列 inventory；`_incidents/` 22 · `_archive/` 8。

**目标**：根目录仅保留 inventory「支持脚本表」+ 仍被 runtime 引用的脚本；其余 grep 零引用 → `_archive/`（或 postmortem → `_incidents/`）。

**建议分批 grep 规则**（按优先级移）：

| 批次 | 模式 | 目标目录 | 注意 |
|------|------|----------|------|
| A | `gen-*` · `run-portraits*` · `run-blink*` · `run-all-portraits*` | `_archive/` | 头像/占位生成一次性 |
| B | `inbox-*` · `archive-inbox*` · `triage-inbox*` · `close-stale*` · `prune-*` | `_archive/` | 查 scheduler jobs 是否引用 |
| C | `test-codex-web*` · `test-lingxiao*` · `test-app-server*` · `inspect-codex*` · `probe-codex*` · `_run_identity_test.py` | `_archive/` | identity 实验脚本 |
| D | `round1-*` · `round2-*` · `v3-advance*` · `migrate-tasks-to-v3` · `pause-v3*` · `resume-v3*` | `_archive/` | v3 迁移期运维 |
| E | `_*` 前缀（除 `write_reorg_risks.py` 在根的不适用）· `poll-*` · `diag-*` | `_archive/` | 临时 recovery |
| F | 重复 restart（`.ps1`/`.sh` 留 `restart-mailbus.py`）· `keep-awake.ps1` | `_archive/` | |

**必须保留（grep 后再确认）**：

- inventory 支持表 20 条（含 `patch-skills-index-framework.py` — `docker-agents/start-team.sh` 引用）
- `config/scheduler/jobs.json` 引用的脚本路径
- `collect-pipeline-postmortem.py` 引用的 `_incidents/` 路径（移后改文档路径即可）
- `pipeline-e2e-regression.py` · `run-game-lvup-e2e.py` · `test-automation-e2e.py`（E2E/回归）

**每批流程**：

1. `rg "tools/<script_name>" E:/ai_tools --glob "!*venv*" --glob "!_archive/*" --glob "!_incidents/*"`
2. 无 lib/docker-agents/scheduler/CI 引用 → `shutil.move` 到 `_archive/` 或 `_incidents/`
3. 更新 `docs/tools-inventory.md`（剩余数量 + 本批清单）
4. `python -m pytest tests/test_phase4_dashboard.py tests/test_phase38_opencode_e2e.py tests/test_init_store.py tests/test_framework_skills.py tests/test_decomposition.py -v`
5. 根目录文件数目标：**≤30**（最终 ≤20 支持 + 少量过渡）

**顺带关 P6-C02 / #45**（若本批有余力）：

- `mailbus-boot.sh`：仍 DEPRECATED；评估 `scripts/start-all.sh` 改指 `docker-agents/start-team.sh` 后能否移 `_archive/`
- `STANDARD_PROCEDURE.md`：仅保留 quickstart 弃用指针（可不删文件）

**顺带关 P6-C03 / #46**：quickstart 只列支持脚本表；inventory 与 README 对齐。

---

### 🟠 第二优先：环境残留

| 项 | 动作 | 验收 |
|----|------|------|
| docker-agents-mailbus-1 端口 9812≠9814 | `docker compose ... force-recreate`；确认 health 连 9814 | `curl localhost:9814/api/status` 200 |
| WSL localhost NAT | 文档化 E2E 从 Windows 或 WSL 宿主机 IP；必要时 `mail/docs/runbook-wsl-codex.md` 补一节 | live E2E 可复跑 |
| `mailbus-pipeline-e2e.sh` WSL 失败 | 修 primary/env（`MAILBUS_ROOT`/`MAILBUS_DATA`/`lib/api-url.sh`） | 脚本 exit 0 |
| docker-agents/*.sh CRLF | 批量 `dos2unix` 或 git attributes 检查 | bash 无 `$'\r'` 错误 |
| game-courier 12 步全链 | 可选：`submit-game-courier-task.sh` 复跑 | postmortem 对照 |

**9814 相关 grep**（防复发）：

```powershell
rg "9812" E:/ai_tools/mail/docker-agents E:/ai_tools/mail/tools --glob "*.sh"
```

---

### 🟡 第三优先：§十 残留 + 部分完成（tools/环境 完成后）

**§十 未全绿 #1–#40**：#2 Dashboard→agent.json · #5 org 双轨 · #6 compose-volumes · #8 privilege · #9 Iteration Engine · #11 team-memory env · #14 launch 块 · #24 workspace→access · #28 CLI MAILBUS_DATA · #29 watchdog

**部分完成**：P3-S02 S05 S06 S07 S09 S10 S12 S13 S15 S21 S29 S32 S33 S35 P3-R03 R06 R12 R15 P5-R02

**观察项（文档化即可）**：P3-S01 S04 S08 S11 S20 S22 S26 S27 S37 S49 · P5-R06 R07 R08 · P2-R06 R07 · P0-R03

---

## 关键路径

| 用途 | 路径 |
|------|------|
| 风险登记 | `mail/plans/reorg-risks-by-phase.md` |
| tools 盘点 | `mail/docs/tools-inventory.md` |
| scheduler jobs | `mail/config/scheduler/jobs.json` |
| API 端口 env | `mail/docker-agents/lib/mailbus-env.sh` · `lib/api-url.sh` |
| live E2E | `mail/tools/live-dali-opencode-e2e.py` · `verify-live-dali-e2e.py` |
| game-courier | `mail/docker-agents/submit-game-courier-task.sh` |

## 验收命令

```bash
cd E:/ai_tools/mail
python tools/write_reorg_risks.py
python -m pytest tests/test_phase4_dashboard.py tests/test_phase38_opencode_e2e.py tests/test_init_store.py tests/test_framework_skills.py tests/test_decomposition.py -v
python tools/verify-live-dali-e2e.py --task-id p5-dali-live-20260626-155940
# tools 根目录计数（目标 ≤30）
python -c "from pathlib import Path; print(len([f for f in Path('tools').iterdir() if f.is_file()]))"
Test-Path E:/ai_tools/store   # False
rg "mail/adapters" mail/lib --glob "*.py"   # 仅 reject，非 SoT 读取
```

## 汇报格式

**做了什么 / 移了哪些脚本（附 rg 证据）/ tools 根目录剩余数 / 测了什么 / 关了哪些风险 ID / 环境项验收结果**
```

---

## 变更记录

| 日期 | 内容 |
|------|------|
| 2026-06-26 | Phase 6 首轮 + decomposition |
| 2026-06-26 + | 下一会话：tools 第二批 + 环境残留 |
