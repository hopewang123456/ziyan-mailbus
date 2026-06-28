# game-courier-20260625 — 12 步 Live 验收复盘

> 任务：`game-courier-20260625`（信使迷宫终端小游戏 · mailbus 12 agent 全员 live）  
> 终态：**success**（12/12 step 落盘 + `acceptance.json`）  
> 复盘时间：2026-06-25  
> 结构化数据：`store/msg-results/game-courier-20260625-postmortem.json`

---

## 1. 交付物

| 路径 | 说明 |
|------|------|
| `store/deliverables/game-courier-20260625/` | 游戏源码 + 测试 + 方案/调研 |
| `store/msg-results/game-courier-20260625/step-s*.json` | 12 步 pipeline 结果 |
| `store/msg-results/game-courier-20260625/acceptance.json` | 终验归档 |
| `logs/pipeline-watch-game-courier-20260625.log` | 后台盯盘日志 |

---

## 2. 问题清单（按严重度）

### P0 — 导致步骤卡死或 phantom 完成

| ID | 步骤 | 现象 | 根因 | 修复/缓解 | 建议 |
|----|------|------|------|-----------|------|
| **container-path-push** | s10 | 灵巡 Hermes `pushed` 久无 `step-s10.json`，容器内进程挂着 | 推送正文含 `E:\ai_tools\mail\store\...`，容器只能读 `/mailbus/store/...` | `to_container_store_path` + `rewrite_host_store_refs`；`pipeline_trigger` 写 inbox 时转换 | **已合入**；Hermes/OpenClaw/Codex 凡 `container_service` 的 agent 统一走该路径 |
| **inbox-closed-no-result** | s6 等 | inbox `closed/done` 但无 `step-s*.json`，链永久卡住 | CLI 结束未落盘，scanner 仍标完成 | reset 脚本 + phantom 检测 + verify 门禁 | 推送成功必须进 `processing`；CLI 结束强制 `verify_pipeline_step_delivery` |
| **phantom-cooldown** | 多步 | phantom 重置 `pending` 后仍 15min 不重推 | 重置未清 `last_pushed_at` | scanner 重置时清 `last_pushed_at`；`pushed_count=0` 跳过冷却 | 保留；加监控「pending + pushed_count>0 + 无结果」 |
| **lingjian-bwrap** | s8 | 灵鉴 Codex 静默失败，无 reply | WSL 无 user namespace，`workspace-write` 内 bwrap 失败 | `lingjian` 配置 `danger-full-access`；pipeline 用 `deepseek-flash` | 文档化 WSL `kernel.unprivileged_userns_clone=1`；或审查步默认 full-access |
| **codex-slot-contention** | s8 | 主 pipeline 与 side-audit 争 Codex 单槽 | `dispatch_pending_audits` 无 primary 互斥；`cli_active` 任意 codex 即 true | `side_audit_deferred_for_reviewer`；`cli_active_in_ps_for(msg_id)` | 主 pipeline running 时默认 defer 全部 audit-req |
| **llm-gate-after-explicit-chain** | s12 后 | 12 步全完成但 task 仍 `running/blocked` | `llm_adaptive` 的 `llm_step_confirm` 在末步后尝试 spawn s13 | 手动 skip gate + `apply_accept` | **显式 `planned_role_types` 耗尽且末步 approved → 直接 terminal，不走 llm_route** |
| **deliverable-no-interactive** | s5–s6 | README 写「交互模式」但无法选路线；`run_game(auto=)` 未实现 | 验收仅 `pytest` + `--auto`；`engine.run_game` 忽略 `auto` 参数；`main` 非 auto 分支仍 `run_game(auto=True)` 一次跑完 3 轮 | `tools/patch-courier-interactive.py` 补 `run_round` + 每轮 `input` 选 A/B/C | **门禁增加交互 E2E**；step 工单引用 scheme 玩法条款；禁止仅 auto 即标 done |

### P0 — 交付物与验收缺口（产品向）

| ID | 步骤 | 现象 | 根因 | 修复/缓解 | 建议 |
|----|------|------|------|-----------|------|
| **acceptance-auto-only** | s9–s12 | pipeline `success` 但玩家无法「玩」游戏 | 验收标准只写 `--auto --seed 42`；灵验/灵巡/小七未测 `input()` 路径 | `patch-courier-interactive.py`（post-live） | `verify` 增加 scripted stdin；`step-s9` 须附交互日志 |
| **scheme-playability-not-gated** | s1–s6 | scheme 要求「每轮选路线、分配资源」，实现为 RNG | 开发工单未绑定 scheme 要点；审查/测试未对照玩法 | 同上 + `prepare_round`（post-live） | 工单 `acceptance_criteria[]` 链式引用 scheme |
| **win-ps1-bom** | 交付物 | `.\play.ps1` 报「缺少 `}`」 | `play.ps1` UTF-8 无 BOM + 中文串，PS 5.1 误解析 | `fix-courier-windows-launch.py`（UTF-8 BOM + 英文提示） | s9/s12：Windows 上跑 `.\play.ps1` 语法检查 |
| **win-bat-wrong-default** | 交付物 | 双击 `play.bat` 只见自动演示、非交互 | 交付 `play.bat` 默认 `--auto --seed 42` | `fix-courier-windows-launch.py`（默认交互 + `--plain`） | 验收区分 `play.bat`（交互）与 `play-auto.bat`（演示） |
| **win-ansi-blank** | 交付物 | 终端「像空白/只有空行」 | 未默认 `--plain`；ANSI + Unicode 框线在部分 Win 终端不可读 | `patch-courier-main-win.py` + plain 模式 ASCII 框线 | s9 在 Win cmd/PowerShell 各跑一遍并截图 |
| **win-interactive-flow** | 交付物 | 交互时先空信件、重复 intro | `main` 在 `run_round` 前未 `prepare_round` | `fix-courier-windows-launch.py` | 交互 E2E 断言每轮先见信件再见 `选择路线` |
| **win-launch-missing** | 交付物 | 无根目录快捷启动、无自动演示专用脚本 | pipeline 未要求 Windows 启动矩阵 | `play-courier-game.ps1`、`play-auto.bat`（post-live） | 交付 checklist：bat/ps1/根启动器 + 双击冒烟 |

### P1 — 重试/误报/运维负担

| ID | 步骤 | 现象 | 根因 | 修复/缓解 | 建议 |
|----|------|------|------|-----------|------|
| **win-docker-push** | 全局 | Windows scan 推失败，`docker 不是内部命令` | 宿主机无 docker PATH | `pusher._docker_push_argv()` → WSL `bash -lc` | 验收 checklist：Win 上 `shutil.which('docker')` 与 WSL 双路径探测 |
| **openclaw-timeout-120** | s4 | xiaoqi 推送后无结果 | OpenClaw `--timeout 120` < pipeline 实际耗时 | 对齐 `push_timeout_pipeline` (600s) | 所有 adapter 超时从 `push_timeout_seconds` 读取 |
| **lingyun-powershell-msg** | s6 | Claude Code 推送 4s 失败 ParserError | PowerShell 内联 MSG 含换行/引号 | `try_build_push_direct` 直连 argv | claude_code 禁止 shell 拼 MSG |
| **scanner-assignee-args** | 催办 | 3 次催办误关 pipeline 消息 | `is_current_pipeline_assignee(data_dir, name, tid)` 参数顺序反了 | 已修 + `pipeline_message_protected_from_auto_close` | 单测覆盖参数顺序 |
| **codex-wrong-container** | s8 | 误查 `lingxiao` 容器判断灵鉴 CLI | `agent_cli_active_for` 用默认 service 非 agent.docker.service | 已用 agent 自己的 `docker.service` | adapter 层容器解析单测 |
| **stale-timestamp** | s9 | `step-s9.json` 已写但 FSM 不推进 | result `timestamp` 早于 step `started_at` | 手动改 timestamp 后 trigger | 写 result 时强制 `timestamp >= started_at`；或校验用 mtime 回退 |
| **hermes-pushed-not-processing** | s10 | inbox 长期 `pushed` 非 `processing` | Hermes 未设 `mark_processing_on_task_push` | 已开 | OpenClaw pipeline task 同理评估 |
| **primary-repush-cooldown-15m** | 多步 | CLI 死后 15min 才重推 | `primary_repush_cooldown_minutes=15` | 可配置 | live 验收建议 5–8min；静默失败 8min failover 已补 |
| **subprocess-unicode-wsl** | 推送 | `_readerthread` UnicodeDecodeError | WSL docker 输出非 UTF-8 | communicate 侧 `errors=replace` | Popen 不设 text mode，统一在 saver 线程 decode |

### P2 — 架构/可观测性/省钱

| ID | 现象 | 建议 |
|----|------|------|
| **failover-by-name** | 旧链 `lingjian→lingyun→lingzhao` 不符合工种语义 | 已改为 `role_type` 链：审查(5)→开发(8)→方案(1) |
| **silent-failure-no-alert** | Codex/Hermes 无 reply 时长时间无告警 | `silent_failure_failover` + `push_alert`；pusher 超时写 stderr 到 reply |
| **bus-serve-down** | 仅 watch 在跑，scan 全跳过 | 单 `bus serve` 常驻；watch 只观测不替代调度 |
| **corrupt-remind-tasks** | scan 偶发 UnicodeDecodeError | `json_read` 容错；清理 `remind-*.json` |
| **win-file-lock** | 多进程争用 `ziyan-mailbus-*.lock` | `MAILBUS_LOCK_DIR=store/.locks`；单 serve |
| **watch-result-mismatch** | watch 报 `file step=11 chain=12` | watch 应读 `step-s{N}.json` 而非 legacy 单文件；或按 `step_id` 对齐 |
| **token-burn** | s1–s3 长方案、审查全量读库 | 见 §4；pin flash / 限 `cli_msg_max_chars` |

### 人工介入记录（非代码 bug）

| 步骤 | 操作 | 说明 |
|------|------|------|
| s8 | 灵鉴失败 → 手动 failover 灵云 | 发生在工种 failover 合入前；灵云无 `role_types` 不应作审查替补 |
| s12 后 | skip `llm_step_confirm` + `apply_accept` | 显式 12 步与 `llm_adaptive` 冲突 |

---

## 3. 已合入代码（本轮）

### 3.0 mailbus 运行时（pipeline 内修复，算基础设施）

- `lib/utils.py` — `to_container_store_path`, `rewrite_host_store_refs`
- `lib/agent_adapters.py` — `store_path_for_agent`；Codex 可配置 sandbox/model；Hermes `mark_processing_on_task_push`
- `lib/pipeline_trigger.py` — inbox 任务路径容器化
- `lib/pusher.py` / `lib/commands.py` — pipeline CLI 解析、`data_dir` 透传
- `lib/scanner.py` — assignee 参数、催办保护、recover inbox
- `lib/dispatch/pipeline_step_failover.py` — 工种 failover + 静默失败
- `tools/patch-lingjian-codex-config.py`, `tools/repush-lingxun-s10.py`
- `tests/test_container_paths.py`, `tests/test_pipeline_step_failover.py`

### 3.2 交付物 post-live 人工补丁（**pipeline 未交付，测试未覆盖**）

> 原则：**凡下列脚本改过的文件，均视为 live 验收时未真正交付的能力**；子言/人工试玩后发现的问题，根因是 s9 测试与 s12 验收未覆盖对应路径。

| 补丁脚本 | 改了什么 | 对应缺口 ID | 本应由哪步验收 |
|----------|----------|-------------|----------------|
| `tools/patch-courier-interactive.py` | `engine.run_round`、`input` 选 A/B/C；`main` 交互循环 | `deliverable-no-interactive`, `acceptance-auto-only` | s6 编码自测、s9 灵验、s12 小七 |
| `tools/patch-courier-main-win.py` | `main` Win 控制台 UTF-8/VT；首版 `play.ps1`/`play.bat` | `win-ansi-blank`（部分） | s9 Win 冒烟 |
| `tools/fix-courier-windows-launch.py` | `play.ps1` UTF-8 BOM；默认 `--plain` 交互；`play-auto.bat`；`prepare_round`；plain ASCII 框线；`play-courier-game.ps1` | `win-ps1-bom`, `win-bat-wrong-default`, `win-ansi-blank`, `win-interactive-flow`, `win-launch-missing` | s9 + s12 必须在真实 Windows 双击/PS 试玩 |

**测试遗漏共性**：s9 仅 `pytest` + `python -m game.main --auto --seed 42`（Linux/无头友好），未执行：

- scripted stdin 三轮 `A/B/C`
- Windows `.\play.ps1` / `play.bat` 双击
- `--plain` 与默认彩色模式对照
- scheme 玩法条款 checklist

---

## 3.1 如何玩（交互 vs 自动）

> **说明**：下列玩法依赖 **post-live 人工补丁**（§3.2），**不是** mailbus 12 步当时验收通过的能力。试玩前请先跑 `python mail/tools/fix-courier-windows-launch.py` 或确认交付目录已含补丁后文件。

### 交互模式（自己选路线）

```powershell
cd E:\ai_tools\mail\store\deliverables\game-courier-20260625
.\play.ps1
# 或
.\play.bat
```

每轮会显示：**今日信件**、**快马/驮马**、**三条路线**，提示 `选择路线 [A/B/C]:`，输入 **A**、**B** 或 **C** 回车。共 **3 轮**，最后看满意度是否 ≥ 70。

### 自动演示（验收用，无需操作）

```powershell
.\play-auto.bat
# 或
python -m game.main --plain --auto --seed 42
```

---

## 4. 建议（下一轮 live 前）

### 4.1 必做（门禁）

1. **`check-preflight` 扩展**：claude_code 可达、Codex sandbox 探测、主 pipeline 运行时 audit 队列长度、bus serve 健康。
2. **显式链终态**：`planned_role_types` 为空且最后一步 `approved/done` → 跳过 `llm_step_confirm`，直接 `enter_accepting_or_succeed`。
3. **结果时间戳**：`write_step_result` 默认 `_now_iso()`，禁止 agent 填历史时间。
4. **容器 agent 路径**：CI 断言推送 CLI 正文不含 `E:\` / `C:\`。
5. **交付物玩法门禁**：除 `--auto` 外，必须跑通交互路径（scripted stdin：`A\nB\nC`）；对照 scheme 玩法条款 checklist。
6. **Windows 启动门禁**：`.\play.ps1` 无 ParserError；`play.bat` 默认交互；`play-auto.bat` 自动演示；cmd + PowerShell 各试一次。
7. **step result 引用验收项**：`step-s9` 测试报告须列「交互/自动/Win 启动」三路径，不能仅 pytest。

### 4.2 应做（稳定性）

7. **pusher 超时落盘**：`TimeoutExpired` 时把 stderr 写入 `replies/{agent}.json`，供 `api_stall` / 告警消费。
8. **冷却策略**：primary pipeline `primary_repush_cooldown_minutes` 降至 5–8；与 `silent_failure_failover` 8min 对齐。
9. **watch 脚本**：按 `step-s{id}.json` 校验，消除误报。
10. **灵鉴默认**：`push.pipeline_model=deepseek-flash`，交互 UI 仍可用 reasoner。

### 4.3 省钱（token）

| 阶段 | 建议 |
|------|------|
| 方案/调研 s1–s3 | flash + `cli_combined_max_chars` 限制 |
| 编码 s5–s6 | `prefer_agent: lingyun`（pro 一次到位）或 dali flash 小改 |
| 审查 s7–s8 | 只推变更文件列表 + diff，不全库 |
| 测试 s9 | smoke 子集 + 明确 `pytest` 路径 |
| 运维 | 单 serve + 单 watch，`scan_interval≥30s` |

### 4.4 流程

11. 验收剧本固定：`pytest` → `--auto --seed 42` → **交互三轮（stdin A/B/C）** → **Windows `.\play.ps1` + `play.bat`**。  
12. postmortem 自动化：`collect-pipeline-postmortem.py` 在 task `success` 后 cron 跑一次。  
13. **交付物 diff 审计**：task `success` 后对比 `deliverables/` 与 git 中补丁脚本目标，凡需 post-live patch 即标 `delivery_incomplete`。

---

## 5. 时间线（摘要）

| 时段 | 里程碑 |
|------|--------|
| 01:28–02:59 | s1–s5 方案→拆单→大力编码 |
| 03:00–20:36 | s6–s9 灵云/灵瑾/灵鉴/灵验 多轮卡住与修复 |
| 20:45–21:08 | s10 灵巡路径修复后完成；s11 运营；s12 验收 |
| 21:13–21:16 | 跳过 llm gate，task **success**；watch 自动结束 |

---

## 6. 验收结论

- **Pipeline**：12/12 live 跑通（含人工 failover / gate 跳过）。  
- **游戏（自动）**：`pytest` 4/4；`--auto --seed 42` 满意度 100% 通过——**仅此路径被 pipeline 真正验收**。  
- **游戏（可玩 / 交互 / Windows 启动）**：**live 时未交付**；§3.2 所列补丁均为试玩后人工补上，说明 **s9 测试与 s12 验收不完善**。  
- **判定**：`task=success` ≠ 产品可交付；本轮交付完整度需扣除 §3.2 全部项。  
- **主要技术债**：显式链 vs `llm_adaptive` 终态、容器路径（已修）、Codex 单槽（已部分修）、**验收只测 auto、不测玩法与 Win 启动**。
