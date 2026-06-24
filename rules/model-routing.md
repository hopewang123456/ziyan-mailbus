# 模型分级路由（DeepSeek 省钱策略）

> 更新 · 2026-06-18 · **默认全员 flash**  
> **Tier-2 only**：本文档仅规范 **push 到 Agent（Hermes 等）** 的模型档位。  
> mailbus **内部** Planner LLM 见 `store/rules/mailbus-internal-llm.md`（Tier-1，独立配置与 API Key）。

## 两档模型

| 档位 | config 别名 | Hermes/API 模型 | 适用场景 |
|------|-------------|-----------------|----------|
| **Flash（默认）** | `deepseek-flash` | `deepseek-chat`（V3，便宜快） | **全部** mailbus 推送 task |
| **Pro（ opt-in ）** | `deepseek-pro` | `deepseek-v4-pro` / `deepseek-reasoner` | 仅人工显式开启时 |

## 路由规则（2026-06-18）

1. **默认 flash** — 含 urgent、主 pipeline、审计、灵昭/灵鉴/灵瑾，不再自动升 Pro
2. **Pro 仅当** 同时满足：
   - 消息 `action.model_tier: "pro"`
   - agent 的 `models` 含 `deepseek-pro`
   - 环境变量 `MAILBUS_ALLOW_PRO=1`（防误烧）
3. **agent 未装备 pro** 时，`model_flag` 强制回落 `--model deepseek-chat`，不用 Hermes profile 默认 v4-pro

## 不调用 LLM（零 token）

- `remind-*` / `tracker-remind-*` / `exec-remind-*` 催办
- `patrol-*` / `heartbeat-*` / `confirm-*` / `notice-*` 系统前缀
- `rule-change-*` 规则广播
- 正文含「超时提醒」「inbox_overflow」「执行定时巡检」「生成日报」的 **notice**
- `from: mailbus` 的 notice（task 类型除外）
- `action.no_llm: true` 或 `action.execute: false` 的 notice

**scheduler 巡检/日报**（2026-06-18）：`lingxun_patrol` / `daily_report` 改为零 LLM notice，不再 spawn task。

## Token 预算（`store/config.json` → `token_budget`）

| 键 | 默认 | 说明 |
|----|------|------|
| `scan_interval_idle_seconds` | 300 | 全员无 pending 时 scan 间隔 |
| `scan_interval_active_seconds` | 180 | 有 running 任务或 pending 消息 |
| `scan_interval_urgent_seconds` | 120 | 有加急 pending 或 pipeline 待推 |
| `cli_msg_max_chars` | 600 | 单条消息 CLI 正文上限 |
| `cli_combined_max_chars` | 4000 | 整包 CLI 推送上限 |
| `memory_bridge_limit` | 5 | 每轮记忆同步条数 |
| `memory_bridge_interval_seconds` | 120 | scheduler 间隔 |
| `patrol_interval_seconds` | 3600 | 灵巡巡检间隔 |
| `summary_max_chars` | 200 | pipeline 每步 summary 建议上限 |

动态 scan：`/api/status` → `scheduler.token_activity` / `scan_interval_effective`

## 推送纪律（省 token）

1. task 正文只写 **task_id + 文件路径**，长文放 `store/tasks/` / `msg-results/`
2. 每步 `summary` ≤ 200 字，细节进 `details` 或独立 md
3. 编码重活用 **Cursor 直连**，mailbus 只管流转
4. Pro 仅关键 gate 人工开启，见上节

## 人工 override

| 方式 | 效果 |
|------|------|
| `action.model_tier: "flash"` | 强制 flash |
| `action.model_tier: "pro"` + `MAILBUS_ALLOW_PRO=1` + models 含 pro | 单条 Pro |
| `MAILBUS_DEFAULT_MODEL_TIER=deepseek-flash` | 全局默认（已是默认） |

## 配置

- 根级：`store/config.json` → `"default_model_tier": "deepseek-flash"`
- 12 人 `agents.*.models` 仅保留 `["deepseek-flash"]` 即可
- mailbus 内部 Planner（Tier-1）：`config.mailbus_internal_llm` → 见 `store/rules/mailbus-internal-llm.example.json`

## Tier → Agent 派发（2026-06-25 · 开发工程师 role_type=8）

在 **模型档位** 之外，mailbus 按 tier 过滤 **开发工程师** 候选人，再 least_load + 轮询：

| model_tier | 条件 | 候选池 |
|------------|------|--------|
| **pro** | `MAILBUS_ALLOW_PRO=1` + 消息/Envelope `constraints.dispatch.model_tier: pro` | **灵云** lingyun（+ 装备 pro 的 ling霄） |
| **flash** 或未指定 | 默认 | **大力** dali、**灵霄** lingxiao |
| 显式 prefer | `constraints.dispatch.prefer_agent: lingyun` | 仅 lingyun |

离线 agent（heartbeat `missed_pings≥3`）自动 **forbidden**，failover 换派同 tier 候选人。

显式协作（非默认）：

- `constraints.dispatch.dual_coding: true` → 灵云 + 大力并行首步
- `constraints.dispatch.peer_review: true` → 编码后追加互审步

详见 `lib/dispatch/tier_filter.py`、`rules/execution-order.md`。
