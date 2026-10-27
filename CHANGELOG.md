# Changelog

All notable changes to mailbus are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.

## [Unreleased — 2026-10-26 大版本：指挥席位 + 指标中心 + 管理中心 + 双栈 AI]

规划文档：Vault `Agent/01-mailbus/017-plans/0173-plans/2026-10-26-command-window-metrics-center-dual-cabin-plan.md`（D1-D15 十五决策 + B/AA/PY/R 四组清单）。

### 指挥席位（P1 — 发令交互窗口，D1-D4/D15）
- **发令窗口**（全局抽屉，双舱可唤起）：选职位（`GET /api/positions` 职位目录：候选池+空闲态+inputs 起草表单 schema）→ 动态表单 → `POST /api/tasks/create`（v3 envelope，mode=explicit）→ 空闲优先派发（idle_first 真链路验证）
- **LLM 草稿确认制**：自由需求 → `POST /api/command/draft` 无副作用预演（tier0→internal LLM 同一逻辑）→ 草稿预览（换职位/改理由/调序/删步）→ explicit 多步提交；防幻觉：role_type 合法表过滤 + 空草稿 422 + LLM 不可达显式 503
- **子言真身份（D2/D15）**：`builtin-identities.json` SoT（id/role 稳定、display_name 可改、清单可枚举扩展）；agents 视图运行时合并 → send_msg/inbox 对子言即刻生效（真收件箱验证）；`GET/PATCH /api/identities`
- **被唤起聚合**：`GET /api/command/inbox` 四路合一（manager-pending + human-queue 去重 + 告警 + 子言 inbox）→ 会话流 30s 轮询 + 消息卡内联 FSM 动作按钮（批准/验收/回退）+ ⚡按钮未读徽标

### 指标中心（P2 — B1-B7 开源 BI 取经全落地，双栈同源）
- **metrics manifest 双栈唯一口径真源**（`shared/config/mailbus/metrics-manifest.json`，11 项 A+B 类指标含口径说明；改口径改 JSON 不改代码）
- **python 指标引擎**（`lib/adapters/metrics/`）：collector 现算 + 时序环形存储（7 天窗口）+ 统一查询协议（`GET /api/metrics/query`：point/1h 窗口）+ scheduler 300s 自动采集
- **java Micrometer 对等**：三层（calculator/binder/controller）+ `/actuator/metrics/mailbus.*` 标准暴露（python 无此通道，D8 差异化实证）
- **B4 dashboard as config**：`/api/metrics/layout` hidden 清单——管理中心配置、双舱生效
- **B5 告警规则配置化**：`alert-rules.json` SoT + 规则引擎（触发→写告警+**给子言发消息**，30 分钟去抖）+ 管理中心行内编辑
- **B6 AI 问答走语义层**：LLM 只念注入真值不摸原始数据（真值验证：助手回答与指标引擎一致）
- **驾驶舱三屏统一消费语义层**：首页指标卡（30s 轮询）+ 指标大盘（manifest 驱动网格+sparkline）+ 告警通知

### AI 助手（P2 — D10 双栈对等达成）
- **python**：`POST /api/assistant/ask` 三源上下文（指标真值+RAG 手册+问题）+ citations；复用 internal_llm（langchain 延后：多轮 agent 流需求时引入）
- **java**：spring-ai-starter-model-openai（deepseek/ollama base-url 切换）+ DocsRagService（同源知识库检索）+ 双态 Controller（真/501）；端到端验证（ollama：回答+citations 正确）
- **知识库**：`mailbus/docs/`（架构总览/发令指南 + Vault runbooks 11 篇）

### 管理中心（P3 — 逃生舱重做，D6 双舱分工）
- **`/console`**（/legacy redirect 兼容）：固定侧栏+顶栏标准后台布局（**去星空/星云/3D**，与驾驶舱孪生大屏视觉分野）+ ConsoleKit 设计系统（Table/PageHeader/Tag/Section）
- **七页全真页面**：概览（指标+实体+身份+待办）/ Agent与职位（职位表单 schema 行内编辑 + agent 启停）/ 工作流模板 / 集成 / 指标与报表（规则编辑+布局开关+效率报表）/ 审计与告警 / 诊所
- **职位写端点**：`PATCH /api/positions/{role_type}`（字段白名单+inputs 逐项校验）——发令窗口表单 schema 的管理入口

### 驾驶舱收敛（P4）
- SpaceFlyby 纯氛围飞掠停挂（D6 标准：3D 须映射真实状态；组件保留一行回退）
- 管理类弹窗加「在管理中心打开 →」跳转（弹窗=快捷视图，操作回管理中心）

### 效率度量（P5 — B 类口径）
- `tasks.cycle_avg_minutes`（7 天终态任务周期均值）+ `tasks.interventions_week`（human_gate.resolve 介入数）+ 管理中心效率报表区

### 架构治理（P0 — D7-D9/D12）
- **版本**：JDK 17→25 LTS + Spring Boot 3.3.5→**4.1.2** + Spring AI 2.0.2 + a2a-java 1.4.0.Final 锁版 + requires-python ≥3.12；docker 基镜像 25-jre
- **python 重构（R1-R4）**：composition.py 1835 行拆 9 文件包（157 符号零缺失）；task_fsm/phantom_detect 归位 application；HarnessContract 下沉 domain（清 3 处反向）；LLM 路由域聚合 `adapters/llm_routing/`；修 handlers_inbox 潜伏死 import
- **L3 配置型装配（D7/D8）**：python 轻量装配器（interfaces 注册表 + composition 查表，~100 行）；java Spring 条件装配（MailbusAiProperties + AiConfig）
- **Boot 4 坑全踩平**：starter-web→webmvc 改名、picocli 无 Boot4 starter（自写 SpringCliFactory）、spring-boot-flyway 独立模块（此前 serve 从未真跑迁移）、Spring AI defaultOptions 收 Builder、**@ConditionalOnBean 在用户配置类不可靠**（改 ObjectProvider 运行期判空）

### 验收（D13）
- python **1017 全绿**（+2 装配器/职位/身份/指标/效率等新测试）/ java BUILD SUCCESS / web tsc+build 过
- 冒烟项目执行：python 8 步全链路（身份→职位→草稿→发令→被唤起→批准→指标→助手）+ java 4 端点（同一 SoT）；冒烟数据已清

## [java-v0.1.0] — 2026-10-16

First tagged release of the Java implementation (preview; Python stays the
stable one during dual-run). Milestones M1-M3 complete:

- M1 storage: files-as-SoT shards + SQLite index (Flyway V1-V4), python
  store migration (918 real messages, idempotent), demo chain, trace/archive
- M2 ops: typed event stream, patrol scheduler, notify channels (webhook +
  file digest), acceptance with serve probe, OpenAPI contract (11 paths),
  cockpit SPA hosted on the java serve
- M3 frameworks: agent cards, declarative argv push, run_target dispatch
  (windows/wsl/linux/docker, WSL-verified), transport-card import (14 real
  cards), three-stage test-connection, live claude + container probes
- M4 underway: container image (live-verified), Windows installer,
  dual-run reconciliation tool

## [1.1.0] — 2026-10-15

Monorepo restructure: one product, two implementations, pick either.

- The Python implementation moved into `python/` (git mv, history preserved).
  **Breaking for editable installs**: `pip install -e .` now runs inside
  `mailbus/python/`, not the repo root. Language-neutral assets (skills/,
  rules/, access/, docker-agents/, docs/) and store/ stay at the root.
- `java/` scaffold added (mailbus-j, M1 in progress; JDK 17-compatible build,
  ArchUnit layering gates, Flyway V1 on SQLite).
- `web/` cockpit unchanged, shared by both backends via the API contract.
- Root-derivation split: `PROJECT_ROOT` (python tree) vs `REPO_ROOT`
  (repo root; MAILBUS_ROOT default) — all consumers re-pointed.
- Container image rebuilt (WORKDIR /mailbus/python); compose mounts updated.
- Known tail: ~15 path-semantics test failures remain from the move
  (plus the usual Windows file-lock flakes); tracked for follow-up.
  Production acceptance (six checks) and doctor are green.

## [1.0.0] — 2026-10-03

First stable release: the bus survived a week of real production-line
adversity (two multi-day silent outages root-caused and fixed in-tree) and
delivered a complete three-tier game through a 10-agent pipeline with humans
only adjudicating.

### Reach & self-healing (M1)

- Outbound notify channels (desktop toast/notify-send, webhook
  Telegram/DingTalk(signed)/WeCom/generic, SMTP, file digest) with level
  routing and per-channel failure isolation; `mailbus notify test` for
  reach acceptance.
- Host sentinel (`tools/mailbus_sentinel.py`) watching from outside the
  mailbus process: new warns page immediately (outage drill: detected in
  7.6 min, target ≤10), persistent warns re-remind daily, recovery
  notifies, daily digest; Windows scheduled-task installer, Linux
  systemd-timer instructions.
- `mailbus acceptance status`: six health checks over the store (serve API,
  scheduler heartbeat, patrol/daily report continuity, token ledger,
  human-queue backlog) with machine-readable `--json`.
- Alerts wired: critical/warn alerts, scheduler job fail-streaks (default 3),
  abnormal adjudication entries (station vacancy / push budget / task
  timeout) all page the owner.

### Production-line reliability (M2)

- First-dispatch idempotency: a spawned work order is marked pushed in the
  agent inbox, so scan never pushes the same order twice; spawn failure
  leaves it pending with scan as the fallback pusher (at-least-once intact).
- Receipt tolerance: flat-path contract deliveries
  (`msg-results/msg-<task>-<step>.json`) and `status: done` receipts are
  digested (previously silently starved an 11-day task).
- Timeout escalation: exhausted reminders now escalate into the human
  adjudication queue and page the owner instead of dying as a bare status.
- Blocked-state recovery: chains resumed after adjudication gates
  (owner confirmation) continue expanding their planned stations;
  reminder loop exempts blocked tasks.
- `production-line` task template codifying the game-delivery line
  (planner → developer → reviewer → developer → integration → QA →
  reviewer → docs); station vacancy blocks at zero token.

### Outage fixes (root-caused from the 2026-09 incidents)

- In-container scan no longer dies on a claude push: the Windows PowerShell
  bridge is host-only and skipped inside containers; per-agent push
  exceptions are isolated so one poison message cannot starve the queue
  (3,680 consecutive scan failures were the symptom).
- Manager desk accept actions sent an invalid body (missing `decision`)
  and always failed silently — fixed, live-verified through four final
  acceptances.
- daily_report cron default moved out of the overnight host-sleep window.

### First-run experience (M3)

- Clean-clone drill: `pip install -e .` → `mailbus init` → `mailbus demo`
  completes a full work-order loop in ~7 s with zero dependencies.
- `mailbus doctor` available in the main CLI (self-diagnosis right after
  install, same engine as `mailbus-ops doctor`).

## [0.2.0] — 2026-09-20

Architecture upgrade waves 0–5 (18 slices), all CI-gated:

- Station-based dispatch (registry, vacancy adjudication, pin priority),
  task-flow template library, push budget circuit breaker + DLQ + forward
  hop limits, token ledger with per-task drill-down, message lifecycle
  trace replay, unified human adjudication queue, three-stage connection
  test, assembly cards, five-step onboarding collapsed to one, zero-dep
  demo + first-run wizard + README quick start.

## [0.1.0] — 2026-09-12

Initial public shape: file-based agent-to-agent message bus, adapters for
Hermes / OpenClaw / Codex / OpenCode / Claude Code, CLI, HTTP API, cockpit
dashboard.
