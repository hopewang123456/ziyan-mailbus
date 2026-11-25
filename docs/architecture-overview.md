# mailbus 架构总览（AI 助手知识库 · 2026-11-24）

mailbus 是 AI agent 消息总线：Python FastAPI + SQLite 后端（`python/mailbus/`），file-bus / MCP / A2A 三种传输，共用 React 驾驶舱（`web/`）。

## 分层（python 侧）

```
core → application → adapters → api → bootstrap
```

- `core/` — 纯领域（`agents` / `approval` / `collab` / `identity` / `messaging` / `metrics` / `org` / `skills` / `workflow` / `shared`），仅标准库
- `application/` — 用例编排（同域子包 + `dispatch` / `queries` / `settings`），一个用例一个事务，状态变更与 outbox 同事务提交
- `adapters/` — 端口实现（`persistence` 的 SQLite 仓储、`transport` 的 file_bus / MCP pull / A2A、`system` 的时钟与 id）
- `api/` — HTTP 转换（`routers` / `schemas` / `mappers`），只解析调用者，不含权限规则
- `bootstrap/` — 装配与路径（`main` / `container` / `settings`），唯一知道文件路径的层

## 关键概念

- **能力鉴权**：每个写用例首行调用 `core.identity.policy.ensure_allowed(subject, capability, resource)`；api 层仅 `deps.get_actor` 做 token→Actor；写路由必须声明 capability（守卫 G8）
- **Outbox 模式**：一个用例 = 一个 `SqliteUnitOfWork`（每 UoW 新建 WAL 连接）；后台调度按 `ops_outbox` 重试投递
- **组织归属**：员工的团队/岗位只能经邀请码带入，入伙本身不带归属；删除团队/岗位时校验工位引用与在册员工引用，命中返回 409，已注销员工的 `team_id` / `position_id` 自动置空后再删
- **公开脱敏面**：`/api/public/*` 供大屏与工位看板使用，不暴露员工标识
- **A2A**：对齐 Google A2A JSON-RPC 1.0，入口在 `api/routers/a2a.py`

## 常用端点

全量见 `shared/contracts/generated/openapi.json`。

> **状态说明**：本节端点反映当前已实现的旧契约，仅作现状参考。目标契约以 [agent-unification-design.md](design/agent-unification-design.md) 为准：组织使用 `/api/employees`、`/api/positions`、`/api/teams`，任务推进使用 `claim / result / cancel / rerun-join`，不再有 `/api/org/*`、`/api/identity/staff`、`/advance`、`/dispatch`。

- 组织：`GET/POST/DELETE /api/org/teams`、`GET/POST/DELETE /api/org/positions`、`GET/PATCH /api/org/seats`
- 身份：`POST /api/identity/bootstrap/super-admin`、`POST /api/identity/invites`、`POST /api/identity/staff`、`GET /api/identity/me`
- 任务：`POST /api/tasks`、`POST /api/tasks/{id}/advance`、`POST /api/tasks/{id}/dispatch`
- 流程：`POST /api/workflows`、`POST /api/workflows/{id}/versions/{version}/publish`
- 协同：`GET/POST /api/collab/screens`、`GET/POST /api/collab/pairs`、`GET /api/public/collab/seats/{seat_id}/tasks`
- 指标：`GET /api/metrics/manifest`、`GET /api/metrics/query`、`PATCH /api/metrics/rules/{rule_id}`
