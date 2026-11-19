# mailbus 架构总览（AI 助手知识库 · 2026-10-26）

mailbus 是 AI agent 消息总线：Python FastAPI + SQLite 后端（`python/mailbus/`），file-bus / MCP / A2A 三种传输，共用 React 驾驶舱（`web/`）。

## 分层（python 侧）
- `lib/interfaces/` — Port 协议层（19 个 Port：TaskFsmPort/HumanGatePort/MessageTransportPort/A2ATransportPort/IntegrationsPort 等 + L3 装配注册表）
- `lib/domain/` — 领域模型（消息状态机/管道步骤/harness 契约），零 Spring/零 adapter 依赖
- `lib/application/` — 用例编排（task_fsm 工作流引擎/pipeline/role_flow 角色流转/harness 运行时/LLM planner）
- `lib/adapters/` — 端口实现与域服务，按 Port 域分子包（config/discovery/frameworks/integrations/internal_llm/llm_routing/locale/metrics/ops/orchestration/plane/results/runtime/transport），见 `lib/adapters/ARCHITECTURE.md`
- `lib/composition/` — 组合根（context/factories + 6 个 facade_* 跨层门面 + L3 轻量装配器）

## 关键概念
- **职位≠角色（D3）**：工单节点按 role_type 职位展示（role-types.json SoT，含候选池与 inputs 起草表单 schema）；派发 pin>空闲优先>轮询（role_resolver）
- **子言（D2/D15）**：内置主仓角色（builtin-identities.json），用户本人；id 稳定 display_name 可改；经 /api/command/inbox 聚合被唤起消息
- **权限**：每个写用例首行调用 `core.identity.policy.ensure_allowed(subject, capability, resource)`；api 层仅 `deps.get_actor` 做 token→Actor
- **Outbox 模式**：一个用例 = 一个 `SqliteUnitOfWork`（每 UoW 新建 WAL 连接）；状态变更与 outbox 同事务提交
- **A2A**：对齐 Google A2A JSON-RPC 1.0，入口在 `api/routers/a2a.py`

## 常用端点
- 发令：GET /api/positions（职位目录+表单 schema）、POST /api/command/draft（LLM 草稿预演）、POST /api/tasks/create（v3 envelope 创建）
- 指挥席位：GET /api/command/inbox（被唤起聚合）、/api/tasks/{id}/fsm/{action}（响应动作）
- 指标：GET /api/metrics/{manifest,query}、POST /api/metrics/snapshot
- 身份：GET/PATCH /api/identities
