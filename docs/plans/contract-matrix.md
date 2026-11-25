# 契约矩阵（唯一字段账本）

> 2026-11-25 · 模板 + 填写规则
> 上游：[backend-execution-plan.md](./backend-execution-plan.md)、[frontend-execution-plan.md](./frontend-execution-plan.md)
> 定位：**页面/按钮 → 接口 → DTO → 权威表列** 的唯一登记处。未登记不实现；改契约必须同 PR 更新本文件。
> 维护：后端维护，前端只读。状态流转：`待填 → 冻结 → 已实现 → 已验收`（废弃标 `已废弃`）。

---

## 0. 全局默认规则（所有行自动适用）

| 项 | 规则 |
|---|---|
| 列表 | 统一 `{items,total,limit,offset}`；不接受裸数组 |
| 时间 | JSON 一律 ISO 8601 UTC；新表 DB 存 TEXT ISO，旧 REAL 表由适配层转换（D-01 已定） |
| 错误 | `{error,error_code,message_zh}` |
| Graph | `{graph,revision}`；`force=true` 仍递增 revision 并写审计 |
| 软删除 | 列表默认过滤；历史详情可读；有活跃 run 返回 409 |
| 权限 | 写路由必须声明 capability；读接口按 `data_scope` 服务端过滤 |
| 公开投影 | 白名单；不返回 `employee_id/agent_id/team_id/team/endpoint/token/created_by` |
| 幂等 | 认领 CAS；结果带 `attempt_no`；A2A 按 `message_id` |
| Agent 生命周期 | 注册记录长期保留，不因离线自动删除；运行态按心跳判在线/离线；仅协同端删除才移除 |
| 分页上限 | `limit` 默认 100，最大 500 |

---

## 1. 列定义

| 列 | 含义 | 填写要求 |
|---|---|---|
| ID | `域-序号`，如 `TASK-05` | 全局唯一，不复用 |
| 域 | 组织/工作流/任务/Agent/大屏/消息/指标/系统 | 与后端域包一致 |
| 页面/入口 | 控制台页面、`/twin` 或 Agent 回调 | 精确到 Tab/按钮 |
| 方法+路径 | 完整路径 | 只登记最终路径，不写旧别名 |
| 用途 | 一句话 | 动词开头 |
| 请求 DTO | query/body 名称与关键字段 | 字段必须能在字段归属表找到 |
| 响应 DTO | 名称 | 复用已有 DTO，不新造同义 |
| 权限 | capability | 读接口写「登录+范围」 |
| 数据范围 | self/team/global/公开 | 写过滤口径 |
| 权威表.列 | 如 `task_tasks.state` | 计算字段写「由…聚合」 |
| 并发/幂等 | 409 条件、attempt、revision | 无则写「—」 |
| 错误码 | 400/403/404/409/410/422/429/503 | 只列该接口会出现的 |
| 状态 | 待填/冻结/已实现/已验收 | 验收后才可标已验收 |

---

## 2. 阻断决策（填矩阵前先定）

| 编号 | 问题 | 现状冲突 | 建议默认 |
|---|---|---|---|
| D-01 ✅ | 新表时间戳用 REAL epoch 还是 TEXT ISO？ | 已裁决（2026-11-25） | **新表 TEXT ISO，旧 REAL 由适配层转换；DTO 永远 ISO**。设计 F1 与迁移评审已同步 |
| D-02 | 屏幕团队与布局参数放哪？ | 有 `config_json` 与独立列两种倾向 | 只放 `config_json.team_id/layout_type/theme/resolution/play_state` |
| D-03 | 屏幕密钥是否可回显？ | 014 明文 vs 哈希决策 | 只存 `secret_hash`，明文仅登记响应一次 |
| D-04 | 产物存储介质 | 未定 | 本地磁盘 `data/` + 24h 签名 URL |
| D-05 ✅ | 限速是否多实例共享 | 已裁决（2026-11-25） | **本期单实例内存实现**；限速/SSE 容量走端口抽象，为 Redis 预留适配位，不引入依赖 |

> D-01 已裁决；D-02~D-05 为当前默认值，如需调整在对应行标注。

---

## 3. 示例：任务域（可直接照此填写）

### 3.1 接口矩阵

| ID | 域 | 页面/入口 | 方法+路径 | 用途 | 请求 DTO | 响应 DTO | 权限 | 数据范围 | 权威表.列 | 并发/幂等 | 错误码 | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TASK-01 | 任务 | 任务中心·全部 | `GET /api/tasks` | 列表查询 | query：`state,owner_id,workflow_id,limit,offset` | `TaskListOut(items=TaskSummaryOut[])` | 登录 | self/team/global | `task_tasks` | — | 400/403 | 已实现 |
| TASK-02 | 任务 | 任务中心·新建 | `POST /api/tasks` | 创建并立即启动 | `TaskCreateIn`：`title,workflow_id?,owner_id?,variables?` | `TaskDetailOut`（含首个 run） | `task_create`；代派加 `task_dispatch` | self | `task_tasks` + `task_node_runs` | 创建即启动，无草稿 | 400/403/422 | 已实现 |
| TASK-03 | 任务 | 导航角标 | `GET /api/tasks/summary` | 待办角标 | — | `TaskSummaryOut`：`claimable,mine_open,approvals` | 登录 | self | 由 run/approval 聚合 | — | 403 | 已实现 |
| TASK-04 | 任务 | 任务详情 | `GET /api/tasks/{task_id}` | 详情 | path | `TaskDetailOut` | 登录 | self/team/global | `task_tasks` + `task_node_runs` | — | 403/404 | 已实现 |
| TASK-05 | 任务 | 我的工作·认领 | `POST /api/tasks/{task_id}/nodes/{node_id}/claim` | CAS 认领 | path | 待定：`TaskDetailOut` 或 `{run_id,attempt_no}` | 登录 + 岗位候选人 | self | `task_node_runs.assigned_employee_id` | 已被认领返回 409 | 403/404/409 | 已实现 |
| TASK-06 | 任务 | 当前 run·提交 | `POST /api/tasks/{task_id}/nodes/{node_id}/result` | 提交结果/产物 | `ResultIn`：`attempt_no,result,artifact_ids?` | 待定 | `result_submit` + 当前执行人 | self | `task_node_runs.result` | stale attempt 409 | 403/404/409/413 | 已实现 |
| TASK-07 | 任务 | 详情·取消 | `POST /api/tasks/{task_id}/cancel` | 取消任务 | `CancelIn`：`reason` | `TaskDetailOut` | 发起人或超管 | self | `task_tasks.state/termination_reason` | 终态不可取消 | 403/404/409 | 已实现 |
| TASK-08 | 任务 | join·重跑 | `POST /api/tasks/{task_id}/nodes/{node_id}/rerun-join` | 显式重跑汇聚 | `RerunJoinIn`：`scope` | 待定 | 发起人或超管 | self | 新 join attempt + 下游 run | 幂等键待定 | 403/404/409/422 | 已实现 |
| TASK-09 | 任务 | 审批 Tab | `GET /api/approvals` | 待审批列表 | query：`state` | `ApprovalListOut` | `hitl_resolve` | self/team | `task_approvals` | — | 403 | 已实现 |
| TASK-10 | 任务 | 审批卡片 | `POST /api/approvals/{approval_id}/resolve` | 通过/驳回 | `ResolveIn`：`decision,comment` | `ApprovalOut` | `hitl_resolve` | self/team | `task_approvals` | 已处理 409；驳回意见必填 | 403/404/409/422 | 已实现 |
| TASK-11 | 任务 | 产物下载 | `GET /api/artifacts/{artifact_id}/download` | 签名下载 | path | 文件流 | `artifact_read_all` 或本人任务 | self/team/global | `task_node_artifacts` | URL 24h | 403/404/410 | 已实现 |
| TASK-12 | 任务 | 详情·产物 | `POST /api/tasks/{task_id}/nodes/{node_id}/artifacts` | 上传节点产物 | multipart：`file`,`description?` | `ArtifactOut` | `result_submit` + 当前执行人 | self | `task_node_artifacts` + 磁盘 | 单文件 ≤100MB；节点须有执行实例 | 403/404/409/413/422 | 已实现 |

### 3.2 字段归属（任务域）

| 字段 | 唯一来源 | 禁止位置 |
|---|---|---|
| 任务状态 | `task_tasks.state` | 列表 DTO 另存 `status` 同义字段 |
| 当前节点 | 由活跃 run 聚合 | `task_tasks.current_node` 冗余列 |
| 进度 | 由 run 状态聚合 | 任务表冗余计数 |
| attempt | `task_node_runs.attempt_no` | 任务表 |
| 终止原因 | `task_tasks.termination_reason` | 事件表自由文本 |
| 任务产物 | 由 `task_node_artifacts` 聚合 | `TaskDetailOut.artifacts` 仅引用 `ArtifactOut`，不展开文件内容 |

---

## 4. 各域待填骨架

> B1.5「契约桩」已完成；B2–B7 已实现并回填状态，B8 收尾后所有已登记端点均为 `已实现`，无 501 契约桩。
>
> 只给出已知锚点；路径不确定的行标「路径待后端登记」，不得凭记忆先写。

### 4.1 组织域（ORG）

| ID | 方法+路径 | 用途 | 响应 DTO | 权限 | 状态 |
|---|---|---|---|---|---|
| ORG-01 | `GET /api/employees` | 员工列表 | `EmployeeListOut` | `org_manage`/`employee_invite` | 已实现 |
| ORG-02 | `PATCH /api/employees/{employee_id}` | 编辑/绑定 | `EmployeeOut` | 相关权限 | 已实现 |
| ORG-03 | `DELETE /api/employees/{employee_id}` | 软删除 | 204 | `employee_remove` | 已实现 |
| ORG-04 | `GET/POST /api/positions`、`PATCH/DELETE /api/positions/{position_id}` | 岗位 CRUD | `PositionOut` | `org_manage` | 已实现 |
| ORG-05 | `GET/POST /api/teams`、`PATCH/DELETE /api/teams/{team_id}` | 团队 CRUD | `TeamOut` | `org_manage` | 已实现 |
| ORG-06 | `GET /api/options/employees`、`GET /api/options/positions` | 脱敏下拉 | `OptionListOut` | 登录 | 已实现 |
| ORG-07 | `POST /api/employees/invite`、`POST /api/invites/{invite_id}/revoke`、`POST /api/invites/{invite_id}/resend`、`POST /api/invites/accept` | 创建/撤销/重发/接受 | `InviteOut`/`InviteAcceptOut` | `employee_invite`；接受为公开 | 已实现 |
| ORG-08 | `GET/POST /api/roles`、`PATCH/DELETE /api/roles/{role_id}`、`PUT /api/roles/{role_id}/positions`、`PUT /api/roles/{role_id}/employees` | 角色 CRUD 与绑定 | `RoleOut`/`RoleListOut` | `role_manage`/`role_bind` | 已实现 |

### 4.2 工作流域（WF）

| ID | 方法+路径 | 用途 | 响应 DTO | 权限 | 状态 |
|---|---|---|---|---|---|
| WF-01 | `GET/POST /api/workflows` | 列表/新建 | `WorkflowListOut`/`WorkflowOut` | `workflow_create` | 已实现 |
| WF-02 | `GET /api/workflows/{workflow_id}` | 详情/版本 | `WorkflowOut` | 登录 | 已实现 |
| WF-03 | `GET/PUT /api/workflows/{workflow_id}/versions/{version}/graph` | 读/存 Graph | `GraphOut`/`GraphIn` | `workflow_modify` | 已实现 |
| WF-04 | `POST /api/workflows/{workflow_id}/versions/{version}/publish` | 发布 | `VersionOut` | `workflow_publish` | 已实现 |
| WF-05 | `POST /api/workflows/{workflow_id}/versions/{version}/clone` | 派生 | `VersionOut` | `workflow_modify` | 已实现 |
| WF-06 | `DELETE /api/workflows/{workflow_id}` | 软删除 | 204 | `workflow_modify` | 已实现 |
| WF-07 | `GET /api/workflows/{workflow_id}/versions` | 版本列表 | `VersionListOut` | 登录 | 已实现 |
| WF-08 | `POST /api/workflows/{workflow_id}/versions/{version}/validate` | 发布前校验 | `ValidateOut` | 登录 | 已实现 |

### 4.3 Agent / A2A 域（AGT）

| ID | 方法+路径 | 用途 | 响应 DTO | 权限 | 状态 |
|---|---|---|---|---|---|
| AGT-01 | `GET /api/agents` | 外壳列表 | `AgentListOut` | `org_manage` | 已实现 |
| AGT-02 | `POST /api/a2a/messages` | 单入口分发 | `A2aAckOut` | Agent token | 已实现 |
| AGT-03 | `POST /api/agents/{agent_id}/rotate-token`、`POST /api/agents/{agent_id}/revoke-token` | 轮转、吊销 | `AgentTokenOut`/`AgentOut` | `console_admin` | 已实现 |
| AGT-04 | `POST /api/agents/{agent_id}/endpoint/approve`、`POST /api/agents/{agent_id}/endpoint/reject` | 批准/拒绝 | `AgentOut` | 超管 | 已实现 |
| AGT-05 | `GET/POST /api/agent-invites`、`POST /api/agent-invites/{invite_id}/revoke` | 生成/作废 | `AgentInviteOut` | `console_admin` | 已实现 |

### 4.4 大屏域（SCR，完整示例）

> 036 后：密钥只存哈希，明文仅在登记响应返回一次；管理端与公开端共用 `ScreenService`；公开投影不含 `team`。

#### 4.4.1 接口矩阵

| ID | 入口 | 方法+路径 | 用途 | 请求 | 响应 | 权限 | 并发/幂等 | 错误码 | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| SCR-01 | `/twin` 首次加载 | `POST /api/public/collab/screens` | 自动登记 | `ScreenRegisterIn` | `ScreenRegisterOut` | 公开，10/min/IP，上限 64 | 带 `screen_id+secret` 且匹配才复用；否则新建，绝不覆盖 | 400/429/503 | 已实现 |
| SCR-02 | `/twin` 心跳 | `POST /api/public/collab/screens/{screen_id}/heartbeat` | 更新在线 | Header `X-Screen-Secret`；body `floor_id?,seat_id?` | `OkOut` | 公开 | 只更新 `last_seen_at`，不建屏 | 403/404/429 | 已实现 |
| SCR-03 | 页面关闭 | `POST /api/public/collab/screens/{screen_id}/leave` | 主动离线 | Header `X-Screen-Secret` | 204 | 公开 | 幂等 | 403/404/429 | 已实现 |
| SCR-04 | `/twin` 拉配置 | `GET /api/public/collab/screens/{screen_id}/config` | 已发布配置 | path | `PublicScreenConfigOut` | 公开 | 只读 `published_config_json` | 404 | 已实现 |
| SCR-05 | `/twin` 拉布局 | `GET /api/public/layout?screen_id=` | 公开布局 | query | `PublicOfficeSiteOut` | 公开 | 按已发布 `team_id` 过滤 | 404 | 已实现 |
| SCR-06 | `/twin` 实时 | `GET /api/public/collab/stream?screen_id=` | 公开 SSE | query | `text/event-stream` | 公开 | 事件白名单；断线退避 | 404/503 | 已实现 |
| SCR-07 | 协同大屏列表 | `GET /api/collab/screens` | 管理列表 | `limit,offset` | `ScreenListOut` | `console_admin` | — | 403 | 已实现 |
| SCR-08 | 配置弹窗 | `PATCH /api/collab/screens/{screen_id}` | 接管/存草稿 | `ScreenDraftIn` | `ScreenConfigOut` | `console_admin` | 草稿 last-write-wins + 审计 | 403/404/409/422 | 已实现 |
| SCR-09 | 发布按钮 | `POST /api/collab/screens/{screen_id}/publish` | 发布配置 | `ScreenPublishIn` | `ScreenPublishOut` | `console_admin` | `expected_config_version` CAS，冲突 409 | 403/404/409/422 | 已实现 |
| SCR-10 | 远程聚焦 | `POST /api/collab/screens/{screen_id}/focus` | 定向投送 | `ScreenFocusIn` | 204 | `console_admin` | 目标离线 409 | 403/404/409 | 已实现 |
| SCR-11 | 删除按钮 | `DELETE /api/collab/screens/{screen_id}` | 删除屏幕 | path | 204 | `console_admin` | 在线删除 409 | 403/404/409 | 已实现 |

#### 4.4.2 DTO 字段

| DTO | 关键字段 | 说明 |
|---|---|---|
| `ScreenRegisterIn` | `screen_id?`, `secret?`, `name?`, `floor_id?`, `seat_id?` | `screen_id+secret` 同时匹配才复用；否则按新屏 |
| `ScreenRegisterOut` | `screen_id`, `screen_secret?`, `config_version` | `screen_secret` 仅新建时返回，之后不可找回 |
| `ScreenHeartbeatIn` | body `floor_id?`, `seat_id?` | 密钥走 Header，不再放 body |
| `ScreenOut` | `screen_id,name,source,online,last_seen_at,config_version,published_config_version,team_bound,play_state` | 管理列表项；不含密钥与 `team_id` |
| `ScreenListOut` | `{items:ScreenOut[],total,limit,offset}` | 统一列表包装 |
| `ScreenDraftIn` | `config?:ScreenConfigIn`, `play_state?` | `play_state` 即时生效；其余存草稿 |
| `ScreenConfigIn` | `layout_type,theme,resolution,team_id?,office?,grid?,custom?` | 结构见 4.4.3 |
| `ScreenConfigOut` | `screen_id,config_version,updated_at,config` | 管理端草稿，含 `team_id` |
| `PublicScreenConfigOut` | `screen_id,config_version,published,layout_type,theme,resolution,team_bound,play_state,office?,grid?,custom?` | 不含 `team_id`，只给 `team_bound` |
| `ScreenPublishIn` | `expected_config_version` | 与当前版本不一致返回 409 |
| `ScreenPublishOut` | `config_version,published_at` | 发布后 `config_version+1` |
| `ScreenFocusIn` | `floor_id`, `seat_id?` | 目标离线 409 |
| `PublicOfficeSiteOut` | 沿用公开布局结构，删除 `team` | 座位字段见白名单 |

#### 4.4.3 `config_json` 结构

```json
{
  "layout_type": "office",
  "theme": "auto",
  "resolution": "1920x1080",
  "team_id": "team_xxx",
  "play_state": "playing",
  "office": { "site_id": "site_main" },
  "grid": { "rows": 4, "cols": 6, "team_id": "team_xxx" },
  "custom": {
    "seats": [
      { "seat_id": "seat_01", "x": 0.12, "y": 0.34, "scale": 1.0, "rotation": 0 }
    ]
  }
}
```

规则：

- `team_id` 只存在于 `config_json` / `published_config_json`，不设独立列，也不进公开响应。
- `layout_type=grid` 必须带 `team_id`；缺失保存/发布 422。
- `play_state` 即时生效、不参与版本比较；其余字段走草稿 → 发布。
- 发布把 `config_json` 快照到 `published_config_json`，`config_version+1`；草稿可继续修改。

#### 4.4.4 字段归属（大屏域）

| 字段 | 唯一来源 | 禁止位置 |
|---|---|---|
| 屏幕团队 | `published_config_json.team_id` | 独立列、公开响应 |
| 布局/主题/分辨率 | `config_json` / `published_config_json` | 重复列 |
| 播放状态 | `config_json.play_state` | 独立列 |
| 在线状态 | `collab_screens.online` + `last_seen_at` | 缓存表 |
| 密钥 | `collab_screens.secret_hash` | 列表、公开响应、日志 |
| 已发布版本 | `collab_screens.config_version` | DTO 内自增 |

### 4.5 消息 / 指标 / 系统（MSG/MET/SYS）

| ID | 方法+路径 | 用途 | 状态 |
|---|---|---|---|
| MSG-01 | `GET /api/messages`、`POST /api/messages` | 消息列表/发送 | 已实现 |
| MSG-02 | `GET /api/messages/{message_id}/trace` | 追迹 | 已实现 |
| MSG-03 | `GET /api/messages/{message_id}` | 详情 | 已实现 |
| MSG-04 | `DELETE /api/messages/{message_id}` | 删除 | 已实现 |
| MET-01 | `GET /api/metrics/manifest`、`GET /api/metrics/query`、`GET /api/metrics/rules`、`GET /api/metrics/rules/{rule_id}`、`PATCH /api/metrics/rules/{rule_id}` | 指标与规则 | 已实现 |
| MET-02 | `GET /api/metrics/overview`、`GET /api/metrics/trend`、`GET /api/metrics/breakdown`、`GET /api/metrics/export` | 概览/趋势/排行/CSV | 已实现 |
| SYS-01 | `GET/POST /api/settings/integrations`、`POST /api/settings/integrations/{name}/invoke`、`GET/POST /api/settings/env`、`POST /api/dev/reload` | 集成与运行配置 | 已实现 |
| SYS-02 | `GET /api/identity/bootstrap`、`POST /api/identity/bootstrap/super-admin`、`POST /api/identity/bootstrap/model-config`、`POST /api/identity/bootstrap/team`、`POST /api/identity/bootstrap/{step}/skip` | 向导 | 已实现 |
| SYS-03 | `GET /api/audit`、`GET /api/audit/{audit_id}` | 审计列表/详情 | 已实现 |
| SYS-04 | `GET /api/alerts`、`POST /api/alerts/{alert_id}/ack` | 告警列表/确认 | 已实现 |
| SYS-05 | `GET/POST /api/alert-rules`、`PATCH/DELETE /api/alert-rules/{rule_id}`、`POST /api/alert-rules/{rule_id}/test` | 告警规则 CRUD/测试 | 已实现 |

---

### 4.6 B1.5 端点总表（OpenAPI 对齐）

> 本表由 `python tools/check_contract_matrix.py` 校验：矩阵 path+method 集合必须与
> `shared/contracts/generated/openapi.json` 完全一致。`C-*` 为冻结契约桩（501），
> `R-*` 为存量保留实现；旧别名（deprecated）不出现在 OpenAPI，也不登记在此。

<!-- B15_TABLE_START -->
| ID | 方法+路径 | 用途 | 请求 DTO | 响应 DTO | 状态 |
|---|---|---|---|---|---|
| C-001 | POST /api/a2a/messages | A2A 单入口 | A2aMessageIn | A2aAckOut | 已实现 |
| C-002 | GET /api/agent-invites | Agent 邀请码列表 | — | AgentInviteListOut | 已实现 |
| C-003 | POST /api/agent-invites | 生成邀请码 | AgentInviteIn | AgentInviteOut | 已实现 |
| C-004 | POST /api/agent-invites/{invite_id}/revoke | 作废邀请码 | — | AgentInviteOut | 已实现 |
| C-005 | GET /api/agents | Agent 外壳列表 | — | AgentListOut | 已实现 |
| C-006 | POST /api/agents/register | Agent 自助注册 | AgentRegisterIn | AgentRegisterOut | 已实现 |
| C-007 | DELETE /api/agents/{agent_id} | 注销 Agent | — | — | 已实现 |
| C-008 | GET /api/agents/{agent_id} | Agent 详情 | — | AgentOut | 已实现 |
| C-009 | POST /api/agents/{agent_id}/endpoint/approve | 批准 endpoint | — | AgentOut | 已实现 |
| C-010 | POST /api/agents/{agent_id}/endpoint/reject | 拒绝 endpoint | — | AgentOut | 已实现 |
| C-011 | POST /api/agents/{agent_id}/health | Agent 健康检查 | — | AgentHealthOut | 已实现 |
| C-012 | POST /api/agents/{agent_id}/revoke-token | 吊销 Agent token | — | AgentOut | 已实现 |
| C-013 | POST /api/agents/{agent_id}/rotate-token | 轮转 Agent token | — | AgentTokenOut | 已实现 |
| C-014 | POST /api/agents/{agent_id}/unbind | 解绑 Agent | — | AgentOut | 已实现 |
| C-015 | GET /api/alert-rules | 告警规则列表 | — | AlertRuleListOut | 已实现 |
| C-016 | POST /api/alert-rules | 创建告警规则 | AlertRuleIn | AlertRuleOut | 已实现 |
| C-017 | DELETE /api/alert-rules/{rule_id} | 删除告警规则 | — | — | 已实现 |
| C-018 | PATCH /api/alert-rules/{rule_id} | 更新告警规则 | AlertRuleUpdateIn | AlertRuleOut | 已实现 |
| C-019 | POST /api/alert-rules/{rule_id}/test | 测试告警规则 | — | AlertRuleTestOut | 已实现 |
| C-020 | GET /api/alerts | 告警列表 | — | AlertListOut | 已实现 |
| C-021 | POST /api/alerts/{alert_id}/ack | 确认告警 | — | AlertOut | 已实现 |
| C-022 | GET /api/approvals | 审批列表 | — | ApprovalListOut | 已实现 |
| R-001 | POST /api/approvals | 发起审批 | ApprovalIn | ApprovalOut | 已实现 |
| R-002 | DELETE /api/approvals/{approval_id} | 撤回审批 | — | — | 已实现 |
| R-003 | GET /api/approvals/{approval_id} | 审批详情 | — | ApprovalOut | 已实现 |
| C-023 | POST /api/approvals/{approval_id}/resolve | 裁决审批 | ResolveIn | ApprovalOut | 已实现 |
| C-024 | GET /api/artifacts/{artifact_id}/download | 产物签名下载 | — | — | 已实现 |
| C-025 | GET /api/audit | 审计日志列表 | — | AuditListOut | 已实现 |
| C-026 | GET /api/audit/{audit_id} | 审计详情 | — | AuditEntryOut | 已实现 |
| R-004 | GET /api/collab/messages | 协同消息列表 | — | — | 已实现 |
| R-005 | POST /api/collab/messages | 发送协同消息 | CollabMessageIn | mailbus__api__schemas__message__MessageOut | 已实现 |
| R-006 | GET /api/collab/pairs | 结对列表 | — | — | 已实现 |
| R-007 | POST /api/collab/pairs | 创建结对 | PairIn | PairOut | 已实现 |
| R-008 | POST /api/collab/pairs/{pair_id}/end | 结束结对 | — | — | 已实现 |
| C-027 | GET /api/collab/screens | 协同大屏列表 | — | ScreenListOut | 已实现 |
| C-028 | DELETE /api/collab/screens/{screen_id} | 删除大屏 | — | — | 已实现 |
| C-029 | PATCH /api/collab/screens/{screen_id} | 接管/保存草稿 | ScreenDraftIn | ScreenConfigOut | 已实现 |
| C-030 | POST /api/collab/screens/{screen_id}/focus | 遥控聚焦 | ScreenFocusIn | — | 已实现 |
| C-031 | POST /api/collab/screens/{screen_id}/publish | 发布大屏配置 | ScreenPublishIn | ScreenPublishOut | 已实现 |
| R-009 | GET /api/collab/stream | 管理端大屏 SSE | — | — | 已实现 |
| C-032 | POST /api/dev/reload | 重载插件 | — | ReloadOut | 已实现 |
| C-033 | GET /api/employees | 员工列表 | — | EmployeeListOut | 已实现 |
| C-034 | POST /api/employees/invite | 邀请真人 | EmployeeInviteIn | InviteOut | 已实现 |
| C-035 | DELETE /api/employees/{employee_id} | 软删除员工 | — | — | 已实现 |
| C-036 | GET /api/employees/{employee_id} | 员工详情 | — | EmployeeOut | 已实现 |
| C-037 | PATCH /api/employees/{employee_id} | 更新员工 | EmployeeUpdateIn | EmployeeOut | 已实现 |
| C-038 | GET /api/employees/{employee_id}/capabilities | 读取员工业务技能 | — | CapabilitiesOut | 已实现 |
| C-039 | PUT /api/employees/{employee_id}/capabilities | 覆盖员工业务技能 | CapabilitiesIn | CapabilitiesOut | 已实现 |
| C-040 | GET /api/employees/{employee_id}/permissions | 读取员工权限 | — | PermissionsOut | 已实现 |
| C-041 | PUT /api/employees/{employee_id}/permissions | 覆盖员工权限 | PermissionsIn | PermissionsOut | 已实现 |
| C-042 | GET /api/employees/{employee_id}/roles | 读取员工角色 | — | RolesOut | 已实现 |
| C-043 | PUT /api/employees/{employee_id}/roles | 覆盖员工角色 | RolesIn | RolesOut | 已实现 |
| R-010 | GET /api/health | 服务健康探测 | — | HealthResponse | 已实现 |
| C-044 | GET /api/identity/bootstrap | 引导向导进度 | — | BootstrapStatusOut | 已实现 |
| C-045 | POST /api/identity/bootstrap/model-config | 配置模型 | ModelConfigIn | BootstrapStatusOut | 已实现 |
| C-046 | POST /api/identity/bootstrap/super-admin | 创建超级管理员 | SuperAdminIn | SessionOut | 已实现 |
| C-047 | POST /api/identity/bootstrap/team | 创建首个团队 | mailbus__api__schemas__org__TeamIn | mailbus__api__schemas__org__TeamOut | 已实现 |
| C-048 | POST /api/identity/bootstrap/{step}/skip | 跳过引导步骤 | — | BootstrapStatusOut | 已实现 |
| R-011 | POST /api/identity/logout | 退出当前会话 | — | — | 已实现 |
| R-012 | GET /api/identity/me | 当前登录员工 | — | EmployeeOut | 已实现 |
| R-013 | GET /api/inbox | 收件箱投影 | — | — | 已实现 |
| C-049 | POST /api/invites/accept | 接受真人邀请 | InviteAcceptIn | InviteAcceptOut | 已实现 |
| C-050 | POST /api/invites/{invite_id}/resend | 重发真人邀请 | — | InviteOut | 已实现 |
| C-051 | POST /api/invites/{invite_id}/revoke | 撤销真人邀请 | — | InviteOut | 已实现 |
| R-014 | GET /api/layout | 孪生办公室布局 | — | OfficeSiteOut | 已实现 |
| R-015 | GET /api/log | 操作日志 | — | — | 已实现 |
| R-016 | POST /api/mcp/messages | MCP 发送 | mailbus__api__schemas__message__MessageIn | mailbus__api__schemas__message__MessageOut | 已实现 |
| R-017 | GET /api/mcp/pull | MCP 拉取 | — | — | 已实现 |
| C-052 | GET /api/messages | 消息检索 | — | MessageListOut | 已实现 |
| C-053 | POST /api/messages | 发送消息 | mailbus__api__schemas__contract__message__MessageIn | mailbus__api__schemas__contract__message__MessageOut | 已实现 |
| R-018 | DELETE /api/messages/{message_id} | 删除消息 | — | — | 已实现 |
| C-054 | GET /api/messages/{message_id} | 消息详情 | — | mailbus__api__schemas__contract__message__MessageOut | 已实现 |
| C-055 | GET /api/messages/{message_id}/trace | 消息投递追迹 | — | MessageTraceOut | 已实现 |
| C-056 | GET /api/metrics/breakdown | 指标对比排行 | — | MetricBreakdownOut | 已实现 |
| C-057 | GET /api/metrics/export | 导出指标 CSV | — | — | 已实现 |
| R-019 | GET /api/metrics/layout | 大盘布局 | — | MetricLayoutViewOut | 已实现 |
| R-020 | PATCH /api/metrics/layout | 更新大盘布局 | MetricLayoutIn | MetricLayoutViewOut | 已实现 |
| C-058 | GET /api/metrics/manifest | 指标口径清单 | — | MetricManifestOut | 已实现 |
| C-059 | GET /api/metrics/overview | 指标概览卡片 | — | MetricOverviewOut | 已实现 |
| C-060 | GET /api/metrics/query | 指标查询 | — | MetricQueryOut | 已实现 |
| C-061 | GET /api/metrics/rules | 告警规则列表 | — | MetricRulePageOut | 已实现 |
| C-062 | GET /api/metrics/rules/{rule_id} | 告警规则详情 | — | MetricRuleOut | 已实现 |
| C-063 | PATCH /api/metrics/rules/{rule_id} | 更新告警规则 | MetricRuleUpdateIn | MetricRuleOut | 已实现 |
| C-064 | GET /api/metrics/trend | 指标趋势 | — | MetricTrendOut | 已实现 |
| C-065 | GET /api/options/employees | 脱敏员工选项 | — | OptionListOut | 已实现 |
| C-066 | GET /api/options/positions | 脱敏岗位选项 | — | OptionListOut | 已实现 |
| R-021 | GET /api/overview | 运营总览 | — | OverviewOut | 已实现 |
| C-067 | GET /api/positions | 岗位列表 | — | PositionListOut | 已实现 |
| C-068 | POST /api/positions | 创建岗位 | PositionIn | PositionOut | 已实现 |
| C-069 | DELETE /api/positions/{position_id} | 删除岗位 | — | — | 已实现 |
| C-070 | GET /api/positions/{position_id} | 岗位详情 | — | PositionOut | 已实现 |
| C-071 | PATCH /api/positions/{position_id} | 更新岗位 | PositionIn | PositionOut | 已实现 |
| C-072 | PUT /api/positions/{position_id}/employees | 岗位分配员工 | BindingIn | PositionOut | 已实现 |
| C-073 | PUT /api/positions/{position_id}/roles | 岗位绑定角色 | BindingIn | PositionOut | 已实现 |
| R-022 | GET /api/public/collab/messages | 公开协同消息（脱敏） | — | — | 已实现 |
| C-074 | POST /api/public/collab/screens | 自动登记大屏 | ScreenRegisterIn | ScreenRegisterOut | 已实现 |
| C-075 | GET /api/public/collab/screens/{screen_id}/config | 公开大屏已发布配置 | — | PublicScreenConfigOut | 已实现 |
| C-076 | POST /api/public/collab/screens/{screen_id}/heartbeat | 公开大屏心跳 | — | OkOut | 已实现 |
| C-077 | POST /api/public/collab/screens/{screen_id}/leave | 公开大屏离线 | — | — | 已实现 |
| R-023 | GET /api/public/collab/seats/{seat_id}/tasks | 公开工位任务（按工位解析员工，不暴露员工标识） | — | — | 已实现 |
| C-078 | GET /api/public/collab/stream | 公开大屏 SSE | — | — | 已实现 |
| R-024 | GET /api/public/collab/tasks/{task_id} | 公开任务详情（脱敏）；可选 owner_id 绑定，未知返回 404 | — | PublicTaskOut | 已实现 |
| C-079 | GET /api/public/layout | 公开孪生布局（脱敏） | — | PublicOfficeSiteOut | 已实现 |
| C-080 | GET /api/roles | 角色列表 | — | RoleListOut | 已实现 |
| C-081 | POST /api/roles | 创建角色 | RoleIn | RoleOut | 已实现 |
| C-082 | DELETE /api/roles/{role_id} | 删除角色 | — | — | 已实现 |
| C-083 | PATCH /api/roles/{role_id} | 更新角色 | RoleIn | RoleOut | 已实现 |
| C-084 | PUT /api/roles/{role_id}/employees | 角色绑定员工 | BindingIn | RoleOut | 已实现 |
| C-085 | PUT /api/roles/{role_id}/positions | 角色绑定岗位 | BindingIn | RoleOut | 已实现 |
| C-086 | PUT /api/seats/{seat_id}/assign | 分配工位 | SeatAssignIn | SeatOut | 已实现 |
| C-087 | GET /api/settings/env | 运行配置 | — | EnvGroupsOut | 已实现 |
| C-088 | POST /api/settings/env | 写入运行配置 | EnvUpdateIn | EnvGroupsOut | 已实现 |
| C-089 | GET /api/settings/integrations | 集成清单 | — | IntegrationsOut | 已实现 |
| C-090 | POST /api/settings/integrations | 增删插件 | PluginActionIn | PluginActionOut | 已实现 |
| C-091 | POST /api/settings/integrations/{name}/invoke | 调用集成动作 | IntegrationInvokeIn | IntegrationInvokeOut | 已实现 |
| R-025 | GET /api/skills | 技能包列表 | — | — | 已实现 |
| R-026 | POST /api/skills | 登记技能包 | SkillPackageIn | SkillPackageOut | 已实现 |
| R-027 | GET /api/skills/effective | 有效技能解析 | — | — | 已实现 |
| R-028 | PATCH /api/skills/{package_id} | 更新技能包 | SkillPackageUpdateIn | SkillPackageOut | 已实现 |
| R-029 | POST /api/skills/{package_id}/bindings | 变更技能绑定 | SkillBindingIn | SkillPackageOut | 已实现 |
| R-030 | POST /api/skills/{package_id}/delete | 删除技能包 | — | — | 已实现 |
| R-031 | POST /api/skills/{package_id}/refresh | 探测技能包来源 | — | SkillPackageOut | 已实现 |
| R-032 | GET /api/stream | 运营事件流（SSE） | — | — | 已实现 |
| C-092 | GET /api/tasks | 任务列表 | — | TaskListOut | 已实现 |
| C-093 | POST /api/tasks | 创建并启动任务 | TaskCreateIn | TaskDetailOut | 已实现 |
| R-033 | GET /api/tasks/audit/stats | 审核统计 | — | AuditStatsOut | 已实现 |
| C-094 | GET /api/tasks/summary | 导航角标 | — | TaskCountersOut | 已实现 |
| C-095 | GET /api/tasks/{task_id} | 任务详情 | — | TaskDetailOut | 已实现 |
| C-096 | POST /api/tasks/{task_id}/cancel | 取消任务 | — | TaskDetailOut | 已实现 |
| C-097 | POST /api/tasks/{task_id}/nodes/{node_id}/claim | CAS 认领节点 | — | TaskDetailOut | 已实现 |
| C-098 | POST /api/tasks/{task_id}/nodes/{node_id}/rerun-join | 显式重跑汇聚 | RerunJoinIn | TaskDetailOut | 已实现 |
| C-099 | POST /api/tasks/{task_id}/nodes/{node_id}/result | 提交节点结果 | ResultIn | TaskDetailOut | 已实现 |
| C-100 | GET /api/tasks/{task_id}/trace | 任务追迹 | — | TaskTraceOut | 已实现 |
| C-101 | GET /api/teams | 团队列表 | — | TeamListOut | 已实现 |
| C-102 | POST /api/teams | 创建团队 | mailbus__api__schemas__contract__org__TeamIn | mailbus__api__schemas__contract__org__TeamOut | 已实现 |
| C-103 | DELETE /api/teams/{team_id} | 删除团队 | — | — | 已实现 |
| C-104 | PATCH /api/teams/{team_id} | 更新团队 | mailbus__api__schemas__contract__org__TeamIn | mailbus__api__schemas__contract__org__TeamOut | 已实现 |
| C-105 | GET /api/teams/{team_id}/seats | 团队工位列表 | — | SeatListOut | 已实现 |
| C-106 | GET /api/workflows | 流程列表 | — | WorkflowListOut | 已实现 |
| C-107 | POST /api/workflows | 创建流程定义 | WorkflowIn | WorkflowOut | 已实现 |
| C-108 | DELETE /api/workflows/{workflow_id} | 删除流程定义 | — | — | 已实现 |
| C-109 | GET /api/workflows/{workflow_id} | 流程定义详情 | — | WorkflowOut | 已实现 |
| C-110 | GET /api/workflows/{workflow_id}/versions | 版本列表 | — | VersionListOut | 已实现 |
| C-111 | POST /api/workflows/{workflow_id}/versions/{version}/clone | 派生新版本 | — | VersionOut | 已实现 |
| C-112 | GET /api/workflows/{workflow_id}/versions/{version}/graph | 读取 Graph | — | GraphOut | 已实现 |
| C-113 | PUT /api/workflows/{workflow_id}/versions/{version}/graph | 保存 Graph | GraphIn | GraphOut | 已实现 |
| C-114 | POST /api/workflows/{workflow_id}/versions/{version}/publish | 发布版本 | — | VersionOut | 已实现 |
| C-115 | POST /api/workflows/{workflow_id}/versions/{version}/validate | 校验 Graph | — | ValidateOut | 已实现 |
<!-- B15_TABLE_END -->

---

## 5. 页面/按钮覆盖清单（防漏）

按 [frontend-requirements.md](../design/frontend-requirements.md) 2.4/2.5 逐项核对，每项必须在矩阵有对应行：

- [ ] 13 个控制台页面各自的首屏数据接口
- [ ] 任务：新建、代派、认领、提交、取消、审批、升级、下载
- [ ] 工作流：新建、保存、派生、发布、删除
- [ ] 组织：邀请、移除、岗位/团队/工位增删改、角色 CRUD、绑定
- [ ] Agent：邀请码、轮转、吊销、endpoint 审批
- [ ] 消息：发送、列表、追迹
- [ ] 大屏：登记、心跳、配置、发布、聚焦、删除、公开 SSE
- [ ] 指标：查询、规则、CSV
- [ ] 系统：审计、告警、集成、技能、设置

---

## 6. 完成判定与 CI

矩阵视为完成需同时满足：

1. 上述覆盖清单 100% 有行；
2. 每条 `响应 DTO` 的字段都能追溯到 `权威表.列` 或明确的聚合规则；
3. 除 §4.6 生成索引外，不存在两个 ID 定义同一 `方法+路径`；
4. 公开接口的响应字段不超出白名单；
5. OpenAPI 导出的 path+method 集合与矩阵完全一致。

CI 建议（后端）：

```text
python tools/export_openapi.py
python tools/check_contract_matrix.py   # 比对 OpenAPI path/method 与本文件
```

> 任一不满足，不得进入该域编码。
