# Agent 统一接入设计

> 2026-11-25 · v4.1（前后端最终需求澄清完成，孪生与协同大屏口径已冻结）
> v1.0 方向 → v2.0 协议与数据模型 → v3.0 结构性冲突消解 → v4.0 跨端契约与安全语义定稿 → v4.1 大屏屏幕模型与公开投影定稿

---

## 0. 决策日志（澄清结论速查）

| # | 议题 | 结论 |
|---|---|---|
| A1 | 接入信息归属 | endpoint / channel_type / endpoint_token / last_seen_at / agent_type 放 **agents 外壳**；pending_task_count / 角色 / 岗位 / 权限放 **identity_employees**；真人 = `agent_id IS NULL`，通道隐含 web，不建 human 外壳 |
| A2 | 节点多次执行 | 新建 **task_node_runs**；支持打回 / 重试 / 并行扇出；扇出全部 done 才算节点成功，全部进入终态后才触发 join；单个失败 run 另建人工补完工作项；result 全留，artifacts 仅打回/重试时删旧（扇出场景全留） |
| A3 | HITL 统一 | **两套分工、两个 tab**：Tab1 审批（仅 `final_approval`，有 tier 与超时）；Tab2 我的工作（human 节点 + Agent 失败转人工）；审批超时 expired，干活不催促但超时**升级通知**，升级只通知、等人决定；中间复用 `human + condition`，不再设普通 `approval` 节点 |
| A4 | 消息与指令 | task_assignment 也落 **msg_messages**（kind=task_assignment）；Agent→mailbus **单入口** `/api/a2a/messages` 按 type 分发；result 只落 `task_node_runs.result` |
| A5 | 命名与绑定 | 权限 → **permission**（全量重命名，含 Java 与契约）；业务技能 → **capability**（角色持多个）；岗位不再存能力；**角色绑员工** |
| B1 | 实例变量 | 新建 **task_variables**；入参只读，系统变量由引擎写；result 存 TEXT，自动识别 JSON |
| B2 | 循环保护 | 按**节点**计数（max_loops 默认 3），超限**转人工决定** |
| B3 | 超时与升级 | 审批 24h / 干活 72h（节点可配）；升级给**团队负责人 + 超管**；新建 **task_escalations** 记录 |
| B4 | 触发源 | API 手动 / 消息触发 / 定时触发 / 大屏登录交互模式发起；匿名 kiosk 不可发起任务 |
| B5 | 任务归属 | `owner_id` = **当前负责人**（随节点变）；`created_by` = 发起人（不变） |
| B6 | 文件权限 | artifacts **仅任务参与者可读**；本地 Agent 给共享路径，外部 Agent 给签发 URL |
| B7 | 清理归档 | 完成后保留 30 天再归档；任务前台只提供取消，不提供物理删除；员工、Agent、工作流均软删除/停用并保留历史，有活跃 run 时返回 409 |
| C1 | 并发派发 | `BEGIN IMMEDIATE` 事务 + 状态 CAS + 唯一约束兜底 |
| C2 | 新增权限 | 新增 5 个：role_manage / role_bind / workflow_publish / escalation_resolve / artifact_read_all |
| C3 | 大屏投影 | 扩现有 `task.updated` 事件 + `/api/public` 员工状态投影；屏幕模型、匿名投影、三布局与定向聚焦见 F18–F21 |
| C4 | Java 跟进 | Python 与 Java **本期同步实现**：Python 先定契约与迁移，Java 按同一契约、同一迁移编号跟进，不允许语义分叉 |
| C5 | 技能包与能力 | 技能包声明 `provides_capabilities`，绑定员工后生效；派活匹配 = **capability 交集非空** |
| D1 | token 轮转 | 手动轮转，旧 token 宽限 24h；**吊销即时失效**（区别对待） |
| D2 | file_bus 格式 | 与 A2a HTTP payload **完全一致**（同一 schema，两种通道一套代码） |
| D3 | MCP 工具集 | **收敛为 4 个**：mailbus_inbox / send / ack / result；删除其余 12 个（task_create/task_fsm/step_result 等，工作流已由引擎驱动） |
| D4 | 可视化编辑器 | **本期做拖拽编辑器**，由本侧实现前端 + 后端 DAG 校验/导入导出 API |
| D5 | 二级升级兜底 | 一级升级无人处理 → **自动终止任务**（CANCELLED），大屏与工单记录原因 |
| D6 | 归档解档 | 仅**超管手动解档**，解档后临时目录展开，有效期 7 天 |
| D7 | 大屏映射 | 节点**投影到现有工位**（seat）；默认取该节点当前负责员工的工位，`wf_nodes.config` 可覆盖 |
| D8 | 编辑器交互 | 独立整页路由；`@xyflow/react` 画布；坐标存 `wf_nodes.pos_x/pos_y`；**显式保存 + 离开提醒**；条件规则构建器与 JSON 双模式；扇出用节点开关（人数 N）而非连线，**扇出节点仅允许 1 条出边、与多出边互斥**；本期只做**只读版本 diff**；prompt 纯文本 + 变量插入 + 实时预览。详见 [workflow-editor-ux.md](./workflow-editor-ux.md) |
| E1–E17 | 后续补充 | 扇出互斥、多出边禁止混合、条件未命中自动终止、真人共享待办、审批或签、定时补跑、离线宽限、编辑器细节、消息触发、结果幂等、MCP 直接切换、任务取消、外部产物上传、Java 同步 — 见 §12 |
| F1 | 最终跨端契约 | 组织路径统一 `/api/employees`、`/api/positions`、`/api/teams`，无旧路径运行时回退；JSON 时间为 ISO 8601 UTC，新表 DB 存 TEXT ISO、旧 REAL 表由适配层转换；列表统一 `{items,total,limit,offset}`；Graph 用整数 `revision` 乐观锁，`force=true` 覆盖保存并审计；错误结构沿用 `{error,error_code,message_zh}` |
| F2 | 任务入口 | `task_create` 可创建本人任务并立即启动；指定他人或代派需 `task_dispatch`；不单独暴露草稿任务页，不提供直接改任务状态或 `/advance` 推进 |
| F3 | 邀请授权上界 | 邀请人只能授予自己有效权限的子集，`data_scope` 不得超过自身；`console_admin`、`*`、`global` 仅超管可授；前端过滤选项，后端强制复核，注册时再次校验 |
| F4 | endpoint 审批 | 注册及 heartbeat 改变 endpoint 后进入待审批并暂停新任务投递，管理员审批后恢复；校验 URL、DNS、元数据地址与可信网段，防 SSRF |
| F5 | 双向 Token 存储 | 当前/旧 token 均用 `MAILBUS_TOKEN_ENCRYPTION_KEY` 加密落库；mailbus 发请求时解密；明文只在签发/轮转时返回，日志与界面只显示指纹；另存不可逆 lookup digest 用于入站反查，不得以“只存哈希”替代密文 |
| F6 | 扇出持久化 | `task_node_runs` 增加 `fanout_slot`：普通节点恒 0，分片为 1..N；唯一键 `(task_id,node_id,fanout_slot,attempt_no)`；分片独立重试，活跃 run 按 `fanout_group` 查询 |
| F7 | 审批节点 | 六类节点中只保留 `final_approval`；删除普通 `approval` 节点引用，中间复核用 `human + condition` |
| F8 | 数据范围 | `self` = 本人发起或曾作为 run/审批参与者；`team` = 当前用户团队任一参与者相关；`global` = 全部。消息按收发双方，产物继承任务，指标与 CSV 复用同一服务端过滤 |
| F9 | 生命周期 | 员工移除、Agent 注销、工作流删除均软删除/停用并保留历史；有活跃 run 返回 409；成功停用时撤销会话/token、退出候选池；任务前台只有取消 |
| F10 | 自由任务 | 包装为一个虚拟执行节点和 run；真人认领/提交结果，Agent 走 A2A result；结果完成后任务 done，不开放直接改任务状态 |
| F11 | 显式汇聚 | 多个前向入边只能进入 `parallel_join`；普通节点直接汇聚会发布报错 `E_MULTI_IN_REQUIRES_JOIN`，回边不计入限制 |
| F12 | join 重跑 | join 等前驱 run 进入终态后统一汇总；missing 分片人工补完后，由发起人或超管显式重跑 join，产生新 join attempt 与下游 run，写审计并展示范围，不自动重跑 |
| F13 | 终验驳回 | `final_approval` 允许零或一条回边；零回边驳回 → `cancelled/approval_rejected`；一回边驳回进入重做；多条回边发布报错 `E_FINAL_REWORK_EDGES` |
| F14 | 外部产物 | 外部 Agent 先 PUT 一次性签名 URL，再在 result 中引用 `artifact_id`，或使用受限 base64 内联；删除 `result.artifacts type=url`，mailbus 不抓取任意外部 URL |
| F15 | 真人邀请 | 链接默认 24h、一次性、可撤销；过期或已使用访问返回 410；重发作废旧链接并生成新链接；注册按邀请快照和服务端授权上界再次校验 |
| F16 | 告警冷却 | `silence_seconds` 是同规则、同资源通知冷却时间，不是每日静默时段；仅进入 firing 通知；webhook/邮件 5 秒超时、指数退避重试 3 次，失败写审计；恢复只置 `resolved`，不发恢复通知 |
| F17 | 旧 Agent 切换 | 现有 6 个 Agent 上线前补岗位、完成 endpoint 审批、签发新 token 并逐一回归；全部准备完成后一次切换并删除旧 transport，不长期保留双引擎 |
| F18 | 屏幕模型 | `/twin` 首次打开自动匿名登记屏幕，`/console/collab` 接管命名、绑定团队、布局与清理；两端共用 `collab_screens` 一张表，管理端不手工新建屏幕 |
| F19 | 大屏访问 | `/twin` 默认匿名 kiosk，只读已发布配置；登录员工可切交互模式，按本人权限与数据范围取数并发起任务；匿名公开投影仅返回姓名、岗位、Agent 名、任务、节点、进度、`seat_id`、结对与气泡，不返回员工/Agent/团队/endpoint/token 等内部标识 |
| F20 | 大屏布局 | `office / grid / custom` 三模式；`grid` 按绑定团队自动生成且必须绑定团队；`custom` 使用控制台可视化编辑器；分辨率仅 1920×1080 / 3840×2160 两档 |
| F21 | 主题与聚焦 | 屏幕配置 `dark/light` 优先，`auto` 按本地时间 19:00–06:00 昼夜；远程聚焦只能定向投送到单块屏幕，一次性指令不改配置 |

---

## 1. 背景与目标

mailbus 是**一人公司的 Agent 协作基础设施**：Agent 通讯管道 + 指令执行管道 + 工作流编排。

现状问题：每接一种 Agent 框架都要在 mailbus 侧写专用推送逻辑（docker exec / CLI / 本地文件），框架越多改动越多；工作流只有线性顺序，无法表达岗位、角色、分支、打回与真人协同。

目标：
1. mailbus 定义 A2a 标准 + 引导模板，Agent 框架侧自行接入
2. 组织架构（岗位 → 角色 → 员工）驱动工作流派发
3. 工作流升级为 DAG（分支 / 并行 / 打回 / 终验），支持 Agent 与真人协同

---

## 2. 概念模型

```
工作流节点(wf_nodes, position_id)
    → 岗位(org_positions)
        → 角色(agent_roles, capabilities[])
            → 员工(identity_employees, 拥有 capability 集合)
                → 外壳(agents, endpoint / channel_type)，员工.agent_id 可为空（真人）
```

**三层职责**

| 层 | 是什么 | 字段归属 |
|---|---|---|
| Agent 外壳 `agents` | 与 mailbus 对接的包装壳，同一外壳所有员工共用接入方式 | endpoint / channel_type / endpoint_token / last_seen_at / agent_type / framework / model |
| 员工 `identity_employees` | 具体执行个体（Agent 内的角色扮演者，或真人） | 岗位 / 团队 / 工位 / 权限 / capability / pending_task_count / 联系方式 |
| 角色 `agent_roles` | 岗位下的能力要求集合，绑定到员工 | capabilities[]（多技能标签） |

**真人**：`identity_employees.agent_id IS NULL`，通道隐含 `web`（协同界面），不建 agents 行。

**配置对象**：配置的是「岗位上挂哪些角色」以及「角色由哪些员工承担」，而非直接配某个 Agent 进程。

---

## 3. 数据模型

### 3.1 新建表

> 时间戳统一使用 `REAL` epoch 秒，与现有 `task_tasks.created_at`、`identity_sessions.issued_at` 保持一致；不使用 TEXT ISO。
> 下文中 `capabilities` 列一律指**业务技能**；权限列一律命名 `permission`。

#### `agent_roles` — 角色定义（技能是多值）
```sql
CREATE TABLE agent_roles (
  role_id      TEXT PRIMARY KEY,
  role_name    TEXT NOT NULL,
  capabilities TEXT NOT NULL DEFAULT '[]',  -- JSON 数组，业务技能标签
  description  TEXT,
  enabled      INTEGER NOT NULL DEFAULT 1,
  icon         TEXT,
  color        TEXT,
  created_at   REAL NOT NULL,
  updated_at   REAL NOT NULL
);
```

#### `employee_capabilities` — 员工实际具备的业务技能
```sql
CREATE TABLE employee_capabilities (
  employee_id  TEXT NOT NULL,
  capability   TEXT NOT NULL,          -- 业务技能标签（如 competition_analysis）
  source       TEXT NOT NULL,          -- manual / skill_package
  granted_at   REAL NOT NULL,
  PRIMARY KEY (employee_id, capability)
);
```

#### `employee_role_bindings` — 员工承担哪些角色
```sql
CREATE TABLE employee_role_bindings (
  employee_id  TEXT NOT NULL,
  role_id      TEXT NOT NULL,
  PRIMARY KEY (employee_id, role_id)
);
```

#### `position_role_bindings` — 岗位绑定哪些角色
```sql
CREATE TABLE position_role_bindings (
  position_id  TEXT NOT NULL,
  role_id      TEXT NOT NULL,
  PRIMARY KEY (position_id, role_id)
);
```

#### `position_employee_assignments` — 管理员覆盖：岗位（某角色）固定给某员工
```sql
CREATE TABLE position_employee_assignments (
  position_id  TEXT NOT NULL,
  role_id      TEXT NOT NULL,          -- 空串 = 该岗位所有角色
  employee_id  TEXT NOT NULL,
  PRIMARY KEY (position_id, role_id)
);
```

#### `employee_contacts` — 真人联系方式
```sql
CREATE TABLE employee_contacts (
  employee_id   TEXT NOT NULL,
  contact_type  TEXT NOT NULL,         -- email / phone / feishu / wechat
  contact_value TEXT NOT NULL,
  PRIMARY KEY (employee_id, contact_type)
);
```

#### `wf_nodes` — 工作流节点定义（替代 wf_versions.nodes JSON）
```sql
CREATE TABLE wf_nodes (
  workflow_id          TEXT NOT NULL,
  version              INTEGER NOT NULL,
  node_id              TEXT NOT NULL,
  name                 TEXT NOT NULL,
  seq                  INTEGER NOT NULL,
  position_id          TEXT,
  node_type            TEXT NOT NULL DEFAULT 'agent',
  prompt_template      TEXT,
  needs_artifacts_from TEXT NOT NULL DEFAULT '[]',  -- JSON：额外需要的前序 node_id
  max_retries          INTEGER NOT NULL DEFAULT 3,  -- 失败重派次数
  max_loops            INTEGER NOT NULL DEFAULT 3,  -- 循环保护上限
  timeout_seconds      INTEGER,                     -- 空则按类型默认（审批 24h / 干活 72h）
  config               TEXT,                        -- JSON：fanout / assignee_id / seat_id / trigger
  pos_x                REAL NOT NULL DEFAULT 0,     -- 画布逻辑坐标（px），与缩放无关
  pos_y                REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (workflow_id, version, node_id)
);
```

`node_type`：`start` / `agent` / `human` / `condition` / `parallel_join` / `final_approval`

#### `wf_node_transitions` — 边（分支 / 并行 / 打回）
```sql
CREATE TABLE wf_node_transitions (
  workflow_id   TEXT NOT NULL,
  version       INTEGER NOT NULL,
  from_node_id  TEXT NOT NULL,
  to_node_id    TEXT NOT NULL,
  condition     TEXT,                  -- JSON 规则，空 = 无条件
  PRIMARY KEY (workflow_id, version, from_node_id, to_node_id)
);
```

#### `task_node_runs` — 节点每次执行实例
```sql
CREATE TABLE task_node_runs (
  run_id               TEXT PRIMARY KEY,
  task_id              TEXT NOT NULL,
  node_id              TEXT NOT NULL,
  attempt_no           INTEGER NOT NULL,       -- 同一 fanout_slot 第几次执行（含打回/重试）
  fanout_slot          INTEGER NOT NULL DEFAULT 0, -- 普通节点恒 0；扇出分片为 1..N
  assigned_employee_id TEXT,
  role_id              TEXT,
  state                TEXT NOT NULL,          -- pending / dispatched / running / waiting_human / done / failed / skipped
  fanout_group         TEXT,                   -- 扇出分组标识；同一扇出的多个 run 共享
  short_fanout         INTEGER NOT NULL DEFAULT 0, -- 凑不齐 N 人时降级执行
  result               TEXT,                   -- 文本，或可解析 JSON
  parent_run_id        TEXT,                   -- 打回时指向上一次 run
  dispatched_at        REAL,
  started_at           REAL,
  completed_at         REAL,
  deadline_at          REAL,                   -- 超时判定
  escalated_at         REAL,                   -- 已升级时间
  UNIQUE (task_id, node_id, fanout_slot, attempt_no)
);
CREATE INDEX idx_task_node_runs_task ON task_node_runs (task_id, node_id);
CREATE INDEX idx_task_node_runs_employee ON task_node_runs (assigned_employee_id, state);
CREATE INDEX idx_task_node_runs_deadline ON task_node_runs (state, deadline_at);
```

#### `task_variables` — 任务实例变量
```sql
CREATE TABLE task_variables (
  task_id     TEXT NOT NULL,
  var_key     TEXT NOT NULL,
  var_value   TEXT NOT NULL,
  source      TEXT NOT NULL,           -- input（入参，只读） / system（引擎写）
  updated_by  TEXT,
  updated_at  REAL NOT NULL,
  PRIMARY KEY (task_id, var_key)
);
```

#### `task_node_artifacts` — 节点产出文件
```sql
CREATE TABLE task_node_artifacts (
  artifact_id   TEXT PRIMARY KEY,
  task_id       TEXT NOT NULL,
  node_id       TEXT NOT NULL,
  run_id        TEXT NOT NULL,
  file_path     TEXT NOT NULL,         -- workspace 内相对路径
  file_name     TEXT NOT NULL,
  artifact_type TEXT,
  description   TEXT,
  created_by    TEXT NOT NULL,         -- employee_id
  created_at    REAL NOT NULL,
  version       INTEGER NOT NULL DEFAULT 1
);
```

#### `task_node_artifact_edits` — 文件修改记录
```sql
CREATE TABLE task_node_artifact_edits (
  edit_id      TEXT PRIMARY KEY,
  artifact_id  TEXT NOT NULL,
  edited_by    TEXT NOT NULL,
  edited_at    REAL NOT NULL,
  version      INTEGER NOT NULL,
  diff_summary TEXT,
  FOREIGN KEY (artifact_id) REFERENCES task_node_artifacts (artifact_id)
);
```

#### `task_escalations` — 超时升级记录
```sql
CREATE TABLE task_escalations (
  escalation_id TEXT PRIMARY KEY,
  task_id       TEXT NOT NULL,
  run_id        TEXT,
  approval_id   TEXT,
  reason        TEXT NOT NULL,         -- approval_timeout / work_timeout / loop_exceeded / run_failed
  level         INTEGER NOT NULL DEFAULT 1,  -- 1 一级 / 2 二级（二级无人处理自动终止）
  escalated_to  TEXT NOT NULL,         -- employee_id / team_leader / super_admin
  escalated_at  REAL NOT NULL,
  resolved_by   TEXT,
  resolved_at   REAL,
  resolution    TEXT
);
```

#### `agent_registration_invites`（Agent 邀请码自助注册）
```sql
CREATE TABLE agent_registration_invites (
  invite_id      TEXT PRIMARY KEY,
  code_hash      TEXT NOT NULL UNIQUE,       -- 邀请码只存哈希，明文仅创建时展示一次
  employee_name  TEXT,                       -- 注册时创建的员工名，空则用 Agent name
  position_id    TEXT,
  capabilities   TEXT NOT NULL DEFAULT '[]', -- 业务技能
  permissions    TEXT NOT NULL DEFAULT '["message_read","message_send","result_submit"]',
  data_scope     TEXT NOT NULL DEFAULT 'self', -- self / team / global，不得超过邀请人范围
  agent_type     TEXT NOT NULL DEFAULT 'external',
  channel_type   TEXT NOT NULL DEFAULT 'a2a',
  expires_at     REAL,                        -- NULL = 长期有效，可手动作废
  created_by     TEXT NOT NULL,
  created_at     REAL NOT NULL,
  used_by_agent_id TEXT,
  used_at        REAL,
  revoked_at     REAL,
  revoked_by     TEXT
);
CREATE INDEX idx_agent_invites_expires ON agent_registration_invites (expires_at);
```

### 3.2 修改现有表

#### `agents`（外壳）
```sql
ALTER TABLE agents ADD COLUMN agent_type TEXT NOT NULL DEFAULT 'service';  -- service / pull_only / external
ALTER TABLE agents ADD COLUMN channel_type TEXT NOT NULL DEFAULT 'a2a';    -- a2a / file_bus / pull_only
ALTER TABLE agents ADD COLUMN endpoint_token TEXT;                    -- 认证加密后的密文，不是明文
ALTER TABLE agents ADD COLUMN endpoint_token_lookup_hash TEXT;        -- 入站反查用不可逆 digest，唯一索引
ALTER TABLE agents ADD COLUMN last_seen_at REAL;
ALTER TABLE agents ADD COLUMN endpoint_token_prev TEXT;              -- 轮转宽限期内的旧 token 密文
ALTER TABLE agents ADD COLUMN endpoint_token_prev_lookup_hash TEXT;  -- 旧 token 入站反查 digest
ALTER TABLE agents ADD COLUMN endpoint_token_prev_expires_at REAL;   -- 旧 token 失效时间（24h）
ALTER TABLE agents ADD COLUMN pending_endpoint TEXT;                 -- 注册/心跳上报的待审批 endpoint
ALTER TABLE agents ADD COLUMN endpoint_review_status TEXT NOT NULL DEFAULT 'pending'; -- pending / approved / rejected
ALTER TABLE agents ADD COLUMN endpoint_approved_by TEXT;
ALTER TABLE agents ADD COLUMN endpoint_approved_at REAL;
ALTER TABLE agents ADD COLUMN deleted_at REAL;                       -- 软注销，保留历史
ALTER TABLE agents ADD COLUMN deleted_by TEXT;
-- endpoint 保存最近一次已审批地址；framework / model / enabled 已有
```

#### `identity_employees`
```sql
ALTER TABLE identity_employees ADD COLUMN pending_task_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE identity_employees ADD COLUMN deleted_at REAL;  -- 软移除，保留历史参与者身份
ALTER TABLE identity_employees ADD COLUMN deleted_by TEXT;
-- endpoint / last_heartbeat 标记废弃（列保留，代码不再读写；接入信息以 agents 为准）
-- 原 employee 级 endpoint_approved 不再作为权威，审批状态迁到 agents
```

#### `identity_capability_grants` → `identity_permission_grants`（全量重命名）
```sql
ALTER TABLE identity_capability_grants RENAME TO identity_permission_grants;
ALTER TABLE identity_permission_grants RENAME COLUMN capability TO permission;
ALTER TABLE identity_invites RENAME COLUMN capabilities TO permissions;
ALTER TABLE identity_invites ADD COLUMN revoked_at REAL;   -- 真人邀请撤销/重发作废旧链接
ALTER TABLE identity_invites ADD COLUMN revoked_by TEXT;
-- 真人邀请默认有效期 24h 由应用层签发；consumed_at 后再次访问返回 410
-- SQLite ≥3.25 双端均满足；保留 granted_at 与 18 行数据，无需搬迁
```

#### `task_tasks`
```sql
-- owner_id 语义明确为「当前负责人」，created_by 为「发起人」，列结构不变
-- 新增循环计数
ALTER TABLE task_tasks ADD COLUMN loop_counters TEXT NOT NULL DEFAULT '{}';  -- JSON: {node_id: times}
-- 终止原因：no_matching_branch / auto_terminated / manual / approval_rejected
ALTER TABLE task_tasks ADD COLUMN termination_reason TEXT;
```

#### `task_nodes`
```sql
ALTER TABLE task_nodes ADD COLUMN current_run_id TEXT;   -- 仅普通单 run 节点的便捷指针；扇出不得以此判定活跃分片
-- state 保留，作为节点聚合态（pending / active / done / failed / skipped）
```

#### `wf_versions` / `wf_defs`
```sql
ALTER TABLE wf_versions ADD COLUMN revision INTEGER NOT NULL DEFAULT 1; -- Graph 乐观锁，每次保存 +1
ALTER TABLE wf_defs ADD COLUMN deleted_at REAL;  -- 工作流软删除，历史任务仍可读
ALTER TABLE wf_defs ADD COLUMN deleted_by TEXT;
```

#### `msg_messages`
```sql
ALTER TABLE msg_messages ADD COLUMN task_id TEXT;   -- 消息触发/任务派发产生的消息回链任务
CREATE INDEX idx_msg_messages_task ON msg_messages (task_id);
-- kind 增加取值：task_assignment / task_cancel（复用现有表）
```

#### `skills_packages`
```sql
ALTER TABLE skills_packages ADD COLUMN provides_capabilities TEXT NOT NULL DEFAULT '[]';
-- 绑定到员工后，自动写入 employee_capabilities(source=skill_package)
```

#### `org_teams`
```sql
ALTER TABLE org_teams ADD COLUMN leader_employee_id TEXT;  -- 超时升级接收人
```

### 3.3 保留不动

`wf_versions`（除新增 `revision` 外结构不变，nodes JSON 废弃不读写）/ `org_positions`（capabilities 列保留不读写）/ `org_seats` / `approval_items` / `collab_screens` / `ops_*` / `msg_delivery_attempts`

---

## 4. 工作流引擎

### 4.1 流转（DAG）

- 节点流向由 `wf_node_transitions` 表达；一个节点可多条出边（并行）、可指回前序（打回）
- **扇出与多出边互斥**：开启扇出（`config.fanout`）的节点只能有 **1 条出边**，且不得同时作为条件分支 / 并行分支的源；"多人并行后再汇总"用「扇出节点 → `parallel_join`」串联表达
- `condition` 为空 = 无条件前进；非空 = 按规则求值选出口；出边 ≥2 时禁止条件边与无条件边混合（校验错误 `E_MIXED_OUT_EDGES`）
- **多个前向入边只能进入 `parallel_join`**；普通节点有超过 1 条前向入边时发布报错 `E_MULTI_IN_REQUIRES_JOIN`。回边用于重做，不计入该限制
- `parallel_join` 等全部前向入边前驱的当前 run 进入终态（done / failed / skipped）后触发，统一汇总完成结果与 missing 分片；不等待后续人工补完
- `start` 自动触发；`final_approval` 通过 → task DONE；驳回仅允许零或一条回边，具体见 4.11

### 4.2 调度（选人选壳）

```
推进节点 node_id:
  1. wf_nodes.position_id → position_role_bindings → role_ids
  2. position_employee_assignments / config.assignee_id 有指定 → 只派给该员工
  3. 否则候选员工 = 具备 role.capabilities 中任意一项（交集非空）
     + enabled + 在线（外壳 online 或真人）
  4. 无候选 → 节点停留，等员工上线后重试
  5. 候选为 Agent 员工 → 按 pending_task_count 升序取第一个
     候选为真人 → 不自动指派，生成共享待办（assigned_employee_id 为空，state=waiting_human）
  6. 创建 task_node_runs 行（attempt_no = 上次数 + 1），写 msg_messages(kind=task_assignment)，入 outbox
  7. 投递按 employee.agent_id → agents.channel_type:
        a2a       → A2aTransport POST endpoint
        file_bus  → FileBusTransport 写本地目录
        pull_only → McpPullTransport 写 pull 目录
        无外壳     → 跳过 transport，写协同界面待办 + SSE（真人）
  8. assigned_employee.pending_task_count + 1

`pending_task_count` 维护：
- 派发 +1；run 进入终态（done / failed / skipped）或任务取消 / 重派时 -1
- 服务启动时按「未终态 run」重算一次，校准漂移
```

真人共享待办：

- 岗位下所有在职真人在「我的工作」看到同一条待办，**先认领先得**
- 认领用 CAS：`UPDATE task_node_runs SET assigned_employee_id=?, state='dispatched' WHERE run_id=? AND assigned_employee_id IS NULL`，影响行数 0 表示已被他人认领，前端刷新列表
- 认领成功后写 `owner_id`（B5：当前负责人随节点变），其余人的待办实时消失（SSE）
- `config.assignee_id` 指定时，只有该员工可见，跳过岗位匹配

### 4.3 并发保护

- 派发在 `BEGIN IMMEDIATE` 事务内完成：读 run → CAS 更新 state（pending→dispatched）→ 写 outbox，同事务提交
- CAS 影响行数为 0 说明被别的 dispatcher 抢走，直接跳过
- `UNIQUE(task_id, node_id, fanout_slot, attempt_no)` 兜底；普通节点 `fanout_slot=0`，扇出分片为 `1..N`

### 4.4 扇出（并行）

- 前置条件：节点**有且只有 1 条出边**；扇出与多出边（并行 / 条件分支）互斥，违反时报 `E_FANOUT_WITH_MULTI_OUT`（校验期拒绝）
- 扇出只决定"同一节点由 N 名员工同时做"，不产生新的下游分支；需要汇总时把唯一出边连到 `parallel_join`
- 一个节点扇出多个 run：共享 `fanout_group`，每个分片使用固定 `fanout_slot=1..N`，`assigned_employee_id` 各不相同；普通节点恒为 `fanout_slot=0`
- 每个分片独立维护 `attempt_no` 和重试次数；同一分片重试递增 `attempt_no`，不占用其他分片槽位
- 活跃 run 以 `fanout_group + fanout_slot` 查询各槽位最新 attempt；`task_nodes.current_run_id` 只用于普通单 run 节点，不作为扇出权威依据
- 完成判定：该 `fanout_group` 内全部槽位的当前 run 都进入终态后，节点进入聚合终态；全部 done 才是节点成功，failed/skipped 分片在 join 汇总中标记 `missing`
- 候选不足：需要 N 人但当前在线候选 M<N 时，节点保持 `pending` 继续等人；节点超时（`timeout_seconds`，未配置默认 10 分钟）仍不足，则按现有 M 人开跑，相关 run 置 `short_fanout=1` 并在汇总上下文标记；M=0 转人工
- 某个 Agent run failed → 原 run 保持 failed 终态，另建人工补完工作项；其余分片不受影响。join 不等待人工补完，先汇总已终态分片并标记 `missing`
- 人工补完会产生对应分片的新 attempt，但**不会自动重跑 join**；由发起人或超管在详情页显式执行「重跑汇聚」，新建 join attempt 与下游 run，写审计并展示本次纳入的分片/attempt 范围
- `loop_counters[node_id]` 仅在走回边重新进入节点时 +1；首次执行与失败重派不计入，避免与 `max_retries` 叠加
- 汇总由 `parallel_join` 节点负责（可配 prompt_template，也可能再派给 Agent 汇总）
- 扇出的 artifacts 全部保留（不删）

### 4.5 打回与重试

| 场景 | attempt_no | 旧产出 |
|---|---|---|
| 打回（走回边再次进入该节点） | +1 | result 保留，旧 artifacts 删除只留最新 |
| 失败重派（max_retries 内换人） | +1 | 同上 |
| 扇出（同节点多员工并行） | 各 run 独立 | 全部保留 |

- 打回时新 run 的 `parent_run_id` 指向被重做的那次 run
- 重派次数超过 `wf_nodes.max_retries`（默认 3）→ 转人工
- 循环保护：`task_tasks.loop_counters[node_id]` 超过 `wf_nodes.max_loops`（默认 3）→ **转人工决定**（继续打回 / 强制通过 / 终止）

### 4.6 条件规则

```json
{
  "and": [
    {"field": "result.score", "op": ">=", "value": 0.8},
    {"or": [
      {"field": "result.status", "op": "==", "value": "approved"},
      {"field": "artifacts.node_req.file_type", "op": "in", "value": ["md", "pdf"]}
    ]}
  ]
}
```

- op：`==` `!=` `>=` `<=` `>` `<` `contains` `in` `not_in` `startsWith` `endsWith` `regex`
- field 路径：`result.*` / `task.*` / `node.*` / `context.*` / `artifacts.<node_id>.*`
- 单条规则可省略 and/or 包裹
- 多出边组合：出边 ≥2 时必须**全带条件**（条件分支）或**全不带条件**（并行分支）；混合 → 校验错误 `E_MIXED_OUT_EDGES`
- **不设隐式默认分支**：全部条件边均未命中时，**任务自动终止**（`task_tasks.state = cancelled`），写 `task_tasks.termination_reason = no_matching_branch`，未完成节点与其 run 置 `skipped`，发 `task.cancelled` 事件（带原因）供大屏与工单展示；不静默卡住、也不自动选第一条
- **安全求值**：只解析 JSON 路径与白名单 op，禁止 eval

### 4.7 result 与变量

- `result` 存 TEXT；mailbus 检测为合法 JSON 则解析供 `result.*` 使用，否则按纯文本
- `task_variables.source=input` 创建后只读；`source=system` 仅引擎写（loop 计数、join 汇总、当前节点）
- Agent 不直接写变量，通过 result 字段影响条件判断

### 4.8 prompt 模板

- 语法 `{{var}}`，可用：`task.*` / `workflow.*` / `node.*` / `role.*` / `previous.result` / `artifacts`
- `artifacts` 渲染为「路径 + 文件名 + 描述 + 产出人」列表；本地 Agent 给绝对路径，外部 Agent 给签发 URL

### 4.9 workspace 与产物

- 目录：`<data_dir>/workspaces/<task_id>/`
- 命名建议：`<seq>_<node_name>_<employee>.<ext>`
- 外部 Agent 产物经签发 PUT URL 落入同一 workspace（见 5.7）；本地 Agent 直接用共享路径
- 保留 30 天后归档（压缩），元数据留在 DB
- 任务前台不提供物理删除；只提供 4.12 的取消。员工、Agent 与工作流的软删除/停用见 13.4，历史 run、result、artifacts 与审计保留

### 4.10 定时触发（start）

- `wf_nodes.config.trigger`：`{"mode": ["manual","message","schedule"], "cron": "0 9 * * 1-5"}`
- cron 为标准 5 段，时区固定 `Asia/Shanghai`（全局可配）；非法 cron 在校验期拒绝（`E_TRIGGER_CRON`）
- 服务重启或调度器恢复后，错过的时间点在 **1 小时内补跑一次**；同一时间点不重复补
- **同一工作流同时只允许一个运行实例**：已有 running 任务时本次触发跳过，记审计 `workflow.trigger_skipped`
- 消息触发仅接受 `kind=command` 且 body 携带 `workflow_id` 与参数的指令消息，发送者必须是已注册员工；同一 `message_id` 只触发一次；普通聊天、广播与系统事件不触发

### 4.11 终验审批（或签）

- 本期仅保留 `final_approval`，不存在普通 `approval` 节点；中间复核用 `human + condition` 表达
- `final_approval` 绑定岗位后，岗位下在职真人均为审批人；`config.assignee_id` 可收窄为单人
- **或签**：任一审批人通过 → task DONE；任一审批人否决 → 按下列回边规则处理
- 终验允许**零或一条回边**：
  - 零回边：驳回后任务 `cancelled`，`termination_reason=approval_rejected`，未完成节点与 run 置 `skipped`
  - 一条回边：驳回后进入该回边指向的重做节点
  - 多条回边：发布校验报 `E_FINAL_REWORK_EDGES`；不成环的前向出边仍报 `E_FINAL_FORWARD`
- 首个处理动作写 `approval_items`（审批人、结论、意见、时间），同事务把其余人的待办置 `cancelled`
- 审批超时 24h → `expired`，不自动通过（见 7.4）

### 4.12 任务取消

- 权限：**发起人（`created_by`）与超管**；其他角色需超管代操作
- 取消时：任务置 `cancelled`、`termination_reason = manual`；未完成节点与其 run 置 `skipped`
- 在跑 run 额外向对应外壳尽力发 `task_cancel`；发送失败不回滚取消，记审计
- Agent 此后提交的结果按 5.6 视为 stale，返回 409

### 4.13 人工节点完成语义

- `human` 节点由岗位真人在「我的工作」认领（CAS，同 4.2），认领后仅本人可提交
- 完成必须提交 `result`（文本或 JSON），可选上传产物；落 `task_node_runs.result` 与 `task_node_artifacts`
- 不设通过/驳回两键；打回由后续条件/审批节点触发，或发起人取消任务
- 提交后 run 置 `done`、`pending_task_count` 归零，按出边推进

### 4.14 外部产物下载

- `download_url` 有效期 24h，与上传 URL 一致；任务重派或 Agent 重新拉取时重新签发
- 过期访问返回 401/403，Agent 重新拉取任务即可获得新链接

---

## 5. A2a 协议

### 5.1 mailbus → Agent（投递到外壳 endpoint）

```
POST <agents.endpoint>
Authorization: Bearer <agents.endpoint_token>
Content-Type: application/json

{
  "message_id": "mb_<uuid>",
  "message_type": "task_assignment",      // task_assignment / notice / task_cancel
  "sent_at": "2026-11-24T14:00:00Z",
  "idempotency_key": "ia_<run_id>",

  "task": {
    "task_id": "task_<uuid>",
    "run_id": "run_<uuid>",
    "attempt_no": 1,
    "node_id": "node_market",
    "node_title": "市场研究",
    "position": "产品经理",
    "role": {"role_id": "...", "role_name": "竞品分析", "capabilities": ["competition_analysis"]},
    "employee_id": "emp_lingzhao",        // 外壳内多员工时必须区分
    "prompt": "分析竞争对手...",
    "context": {
      "previous_result": "...",
      "variables": {"market": "智能硬件"},
      "artifacts": [
        {"artifact_id": "...", "file_path": "01_node_req_lingzhao.md", "file_name": "需求.md",
         "description": "需求文档", "created_by": "emp_lingzhao",
         "download_url": "https://.../artifacts/..."}     // 仅外部 Agent
      ]
    },
    "workspace_dir": "<abs path>",        // 仅本地 Agent
    "deadline": null,
    "priority": "normal",
    "artifact_upload_url": "https://.../a2a/artifacts/upload?exp=...&sig=..."
  }
}
```

### 5.2 Agent → mailbus（单入口，按 type 分发）

**端点**：`POST /api/a2a/messages`，`agent_id` 由 token 推导，不拼路径。

| type | 用途 |
|---|---|
| `message` | 普通消息（沿用现有语义） |
| `result` | 节点结果回推 |
| `heartbeat` | 心跳 / 回传 endpoint |
| `ack` | 受理确认 |

**result 示例**
```json
{
  "type": "result",
  "run_id": "run_<uuid>",
  "attempt_no": 1,                       // 必填：与当前活跃 run 严格匹配
  "status": "completed",                 // completed / failed / needs_human / needs_info / rejected
  "output": "文本或 JSON 字符串",
  "artifacts": [
    {"type": "path", "file_path": "02_compete_lingjin.md", "file_name": "竞品分析.md", "description": "..."},
    {"type": "artifact", "artifact_id": "art_report", "file_name": "report.pdf", "description": "已完成签名 URL 上传"}
  ],
  "completed_at": "2026-11-24T14:03:22Z"
}
```

**heartbeat 示例**
```json
{"type": "heartbeat", "endpoint": "http://192.168.1.100:7890/a2a", "pending_tasks": 0}
```

### 5.3 结果落库

- `result` → `task_node_runs.result`（不写 msg_messages）
- `task_assignment` → `msg_messages`（kind=task_assignment，payload 存 JSON），便于大屏消息流与审计

### 5.4 错误码与重试

| HTTP | mailbus 行为 |
|---|---|
| 202 / 200 | 停止重试 |
| 400 / 401 / 403 / 404 | 不重试，run 标 failed |
| 409 | 幂等命中，取上次结果 |
| 422 | 能力不匹配，换人重派 |
| 429 / 5xx / 网络错误 | Outbox 指数退避（1s→2s→4s→…→最大 10min） |

重试耗尽 → run failed → 计入 `attempt_count`，超过 `max_retries` 转人工。

### 5.5 鉴权
- 注册外壳时生成一个双向 Bearer `endpoint_token`；mailbus→Agent 与 Agent→mailbus 使用同一 token
- `agents.endpoint_token` / `endpoint_token_prev` 保存使用 `MAILBUS_TOKEN_ENCRYPTION_KEY` 加密后的密文，mailbus 仅在向 Agent 发请求时解密；不得保存明文
- `endpoint_token_lookup_hash` / `endpoint_token_prev_lookup_hash` 保存不可逆 digest，仅用于入站 token 反查并建立唯一索引；lookup digest 不能替代密文，否则服务重启后无法构造出站到 Agent 的 Bearer 请求
- `MAILBUS_TOKEN_ENCRYPTION_KEY` 缺失时相关服务必须 fail fast，不自动生成或硬编码默认密钥
- 明文只在签发和轮转成功响应中返回一次；接口、日志、审计和界面不得输出明文，界面仅展示不可逆指纹
- Agent→mailbus 的 `agent_id` 由 token 反查，不接受客户端自报
- 旧 token 轮转后 24h 有效；吊销立即失效，既有规则不变

### 5.6 结果幂等与迟到处理

- 每个 `result` 必须携带 `run_id` 与 `attempt_no`
- 仅当 `run_id` 是当前活跃 run 且 `attempt_no` 匹配时接受并推进
- 旧 attempt / 已完成或已取消 run 的结果 → 409 `stale_run`，写审计 `a2a.result_ignored`，不改任何状态
- 完全相同的结果重复提交 → 200（幂等），不重复推进、不重复写产物
- 缺失 `run_id` 或 `attempt_no` → 400 `E_RESULT_IDENTITY_MISSING`

### 5.7 外部 Agent 产物上传

- 签发：任务分配 / `pull` 响应中按需下发一次性 `artifact_upload_url`（HMAC 签名，含 `run_id`、产物槽位、过期时间）
- 有效期 24h，单文件 ≤100MB；过期后重新签发；URL 单次有效，用后即废
- 上传：`PUT <url>`，body 为文件二进制；成功返回 200 与 `{"artifact_id":"art_..."}`，写 `task_node_artifacts`，并触发 `artifact.updated` 事件
- result 通过 `{"type":"artifact","artifact_id":"art_..."}` 引用已上传产物；`type=url` 已删除，mailbus 不抓取任意外部 URL
- 小文件兜底：`result.artifacts_inline = [{name, mime, base64}]`，单文件 ≤5MB、总计 ≤10MB，超限返回 413
- 外部 Agent 不暴露本地路径；本地 Agent 继续使用共享路径

### 5.8 Agent 注册（邀请码）

```
POST /api/agents/register          # 无需 Bearer，凭邀请码
{ "invite_code": "mbreg_...", "name": "...", "framework": "...", "model": "...",
  "endpoint": "http://...", "health_url": "http://..." }
→ 201 { "agent_id": "...", "employee_id": "...", "endpoint_token": "mbk_...",
        "agent_type": "external", "channel_type": "a2a", "endpoint_review_status": "pending" }
```

- 岗位、`capabilities`、`permissions`、`data_scope` 均取自邀请码，请求体不能提权；邀请创建和实际注册都按 6.4 的授权上界复核
- 注册提交的 endpoint 先写入 `pending_endpoint`，`endpoint_review_status=pending`；管理员审批前可心跳但暂停新任务投递，审批按 7.2 执行
- 同事务创建 `agents` + `identity_employees` + 权限 grants + `employee_capabilities`，任一失败整体回滚
- 邀请码一次性：已用 409、已撤销或已过期 410、不存在 404；默认长期有效，可设 1h/24h/7d 或手动作废；`endpoint_token` 仅返回一次

---

## 6. 权限模型

### 6.1 全量重命名（Permission）

- 代码枚举 `Capability` → `Permission`
- 表 `identity_capability_grants` → `identity_permission_grants`（列 `capability` → `permission`）
- 对外契约字段 `capabilities` → `permissions`（员工权限），Java 同步
- 现有 16 个权限值保持不变（message_send / task_create / ... / console_admin）

### 6.2 新增权限点

| 权限 | 用途 |
|---|---|
| `role_manage` | 角色 CRUD |
| `role_bind` | 岗位/员工绑定角色 |
| `workflow_publish` | 发布工作流版本 |
| `escalation_resolve` | 处理超时升级 |
| `artifact_read_all` | 读取任意任务的产物 |

### 6.3 业务技能（capability）与权限分离

- 权限 = 能做什么动作；capability = 会做哪类业务
- 员工 capability 来源：手工授予 / 技能包 `provides_capabilities` 绑定后自动写入
- 派活匹配：`role.capabilities ∩ employee.capabilities ≠ ∅`

### 6.4 邀请与授权上界

- 真人邀请和 Agent 邀请创建时，邀请人只能授予**自己当前有效权限的子集**；`data_scope` 只能为自身范围或更窄范围（self < team < global）
- `console_admin`、`*` 和 `data_scope=global` 仅超管可授；不新建登录角色表，也不通过前端预设模板绕过该规则
- 前端只展示可授权的权限、角色和范围选项；后端在邀请创建、重发及注册消费时都重新计算上界，拒绝过期快照或后续提权
- 注册使用邀请快照中的岗位、业务技能和权限，但快照不是免校验凭证；若邀请人被降权、停用或邀请被撤销，注册失败
- 所有越权尝试返回 403 并写安全审计，响应不泄露其他员工的权限详情

### 6.5 数据范围（服务端统一判定）

- `self`：本人发起的任务，或本人曾作为任一 run 执行人、认领人或审批参与者的任务；消息仅限当前用户本人是发送方或接收方，不包含仅由团队成员收发的消息
- `team`：当前用户所属团队的任一成员作为发起人、run 参与者或审批参与者的任务；消息按本团队任一成员是发送方或接收方判定，不是仅看任务当前 owner
- `global`：全部任务与消息；仅超管可授予
- 产物继承所属任务范围；指标和 CSV 必须复用同一过滤查询，不得先全量聚合再由前端裁剪
- 所有列表、详情、指标、导出和事件订阅都在服务端执行同一数据范围策略；隐藏按钮不等于授权

---

## 7. 运行时行为

### 7.1 启动

```
apply_migrations（增量）
→ 扫描 agents（enabled）→ 解析 endpoint → probe /health
→ online: last_seen_at=now；offline: 60s 后台重试
```

### 7.2 endpoint 动态发现与审批

支持固定 URL / 容器名（Docker DNS）/ `${ENV}` / 域名；Agent 重启后由 heartbeat 回传更新。

- 首次注册及 heartbeat 检测到 endpoint 变化时，把新值写入 `pending_endpoint`，状态置 `pending` 并暂停该外壳的新任务投递；已有 run 的结果回传仍按 token 与 run 幂等规则处理
- 管理员在控制台查看旧/新 endpoint 后执行审批；审批通过才把 `pending_endpoint` 提升为权威 `endpoint`，记录 `endpoint_approved_by/at` 并恢复新任务投递；拒绝则保持暂停并记录原因
- 注册、审批和实际投递前均校验 URL scheme/端口、DNS 解析结果、链路本地与云元数据地址、可信网段；禁止重定向绕过，连接目标不得落入未授权内网或元数据地址
- 前端不能仅凭 heartbeat 把待审批地址显示为“可用”；必须展示待审批/已拒绝状态，只有管理员可审批

### 7.3 心跳与在线状态

| 类型 | 探活 | 判离线 |
|---|---|---|
| 外壳（a2a） | 30s probe /health | 连续 3 次失败 |
| 外壳（file_bus / pull_only） | 看最近拉取/心跳 | 超阈值 |
| 真人 | 不 probe，取协同界面最后操作时间 | 仅展示"多久未处理" |

离线处理（外壳）：

- 判离线后再等 **90s 宽限期**（继续探活）；宽限期内恢复 → 取消离线处理，run 继续
- 宽限期结束仍离线 → 该外壳名下在跑 run 标 failed（`reason = agent_offline`），按 `max_retries` 换人；耗尽转人工
- 待派任务保持，等外壳恢复后继续投递；`endpoint_token` 被吊销属主动失效，走 11.1，不适用宽限期

注册记录的保留：

- Agent 注册成功后，**记录长期保留**，不会因离线或长时间无心跳被自动删除
- 只有管理员在协同端删除/注销，或主动吊销 token，才移除记录
- 运行态（在线/离线）仍按上表心跳判定，离线宽限与重派照旧

### 7.4 超时与升级

| 类别 | 默认超时 | 超时行为 |
|---|---|---|
| 审批（final_approval） | 24h | 置 expired，通知发起人并记 escalation |
| 干活（human run / 失败转人工） | 72h | 不催本人，升级通知团队负责人 + 超管，只通知不改状态 |
| 循环超限 | — | 转人工决定 |

节点可用 `wf_nodes.timeout_seconds` 覆盖。

### 7.5 大屏投影

**屏幕与配置**

- `/twin` 首次打开自动匿名登记，生成 `screen_id` 与一次性 `screen_secret`；服务端只存 `secret` 的不可逆哈希，明文仅登记响应返回一次；设备写入 `localStorage` 跨重启复用；心跳与离线上报携带 `X-Screen-Secret`；本地无记录或密钥不匹配按新屏登记，绝不覆盖旧屏；`/console/collab` 使用同一 `collab_screens` 表接管命名、绑定团队、布局与清理，不另建管理端屏幕。轮换=删除后重新登记并重新下发。
- 管理端「全屏打开」使用 `/twin?screen_id=...&preview=1`，只读该屏已发布配置，不登记、不发心跳、不接收聚焦；物理大屏仍由设备上的 `/twin` 自动登记。`screen_id` 与密钥不匹配时按新屏登记，绝不覆盖已有配置。
- 屏幕配置分草稿 `config_json` 与已发布 `published_config_json`；保存只写草稿，发布时快照并使 `config_version+1`，`/twin` 只读已发布配置。
- 配置包含 `layout_type`（`office/grid/custom`）、`theme`（`auto/dark/light`）、`resolution`（1920×1080 / 3840×2160）、`team_id`、`play_state`（`playing/paused`）及对应布局数据；公开配置接口不返回 `team_id`，只返回 `team_bound`。
- `grid` 按绑定团队自动生成等距网格，必须绑定团队；`custom` 由控制台可视化编辑器产出布局 JSON；`office` 复用现有办公室布局。
- 心跳 30 秒，60 秒无心跳判离线；仅离线屏幕可删除，在线删除返回 409；仅清理从未被管理端接管且离线超过 30 天的自动登记屏幕；公开登记按 IP 限速 10 次/分钟，在线自动屏上限 64 台。`preview=1` 目标屏不存在返回 404，离线或无已发布配置显示「该屏幕未配置」空态。

**公开投影**

- 默认匿名 kiosk，不显示侧栏、名册、工位抽屉与页脚；登录员工可切交互模式，恢复上述界面并按本人 `permissions` 取数，数据范围取「屏幕绑定团队」∩「本人 `data_scope`」（屏幕未绑定团队时按本人 `data_scope`）；连续 5 分钟无操作自动退回 kiosk，匿名模式不可发起任务。
- 复用 `task.updated` 事件并新增 `screen.config`、`screen.focus`；公开 SSE 只消费 `pair.started / pair.ended / message.created / task.updated / screen.config / screen.focus`，`screen.focus` 只发给目标 `screen_id`。
- 公开字段白名单：姓名、岗位、Agent 名、任务标题、任务状态、当前节点、节点状态、进度、`seat_id`、结对关系、气泡；不返回 `employee_id / agent_id / team_id / endpoint / token / created_by` 与团队名称 `team`，团队只用于服务端过滤；绑定团队后仅渲染该团队成员，其他工位留空。
- 任务状态 `pending/running/blocked/done/cancelled/failed`；工位视觉 `idle/running/waiting_human/failed/done`；同一工位多个活跃节点显示「并发 N」，扇出分片计入 N。
- 结对线取 `collab_pairs.state=active`，由员工或 Agent 侧经既有 `POST /api/collab/pairs` 创建，控制台与大屏均不提供管理入口；气泡合并同层结对消息与 `task_assignment` 摘要（摘要取任务标题，多节点时追加当前节点名），每条结对只显示最新 1 条，前端最多缓冲 3 条，正文截断 40 字，不展示附件与 payload。
- 主题：配置 `dark/light` 优先；`auto` 按浏览器本地时间 19:00–06:00 切换。`prefers-reduced-motion` 时关闭走动人、脉冲与气泡动画。
- 匿名公开面只读，不暴露 artifacts 内容与内部标识；交互模式按当前员工权限与数据范围取数，退出后立即回到 kiosk。

---

## 8. 统一 Agent 引导模板

存 [docs/design/agent-onboarding-template.md](./agent-onboarding-template.md)，内容涵盖：
1. 你要做什么（接收 task_assignment → 执行 → 回推 result）
2. 你不需要做什么（不发现别人、不管工作流、不做重试）
3. 回调单入口 `/api/a2a/messages` + type 分发
4. 幂等（`run_id + attempt_no` 严格校验；同 `message_id` 只触发一次）
5. 心跳与 endpoint 回传
6. 产物读写（本地路径 / 外部签发 URL 上传下载 / result 内联兜底）

登记方式：管理员生成**一次性邀请码**（含岗位、业务技能、权限、`data_scope`、有效期；默认长期有效，可选 1h/24h/7d 或手动作废），Agent 调 `POST /api/agents/register` 自助登记：校验邀请码 → 创建 `agents` 外壳与 `identity_employees` 员工 → 写权限 grants 与 `employee_capabilities` → 返回一次性 `endpoint_token`。邀请码用后即废，重放返回 409；邀请码明文只在生成时展示一次，库中只存邀请码哈希。`endpoint_token` 按 5.8 分别保存加密密文与 lookup digest，不得以“只存哈希”替代；注册提交的 endpoint 按 7.2 写入 `pending_endpoint` 并等待管理员审批，审批前暂停新任务投递。

各框架派生：hermes → skill/rule 模块；Trae/Cursor → MCP 配置；豆包 → system_prompt；元宝 → Skill.md。

---

## 9. 迁移计划

### 9.1 数据库迁移文件（现有 `migrations/NNN_*.sql` 机制）

| 序号 | 文件 | 内容 |
|---|---|---|
| 015 | `015_agents_access_fields.sql` | agents 扩 agent_type / channel_type / endpoint_token / last_seen_at |
| 016 | `016_employee_pending_count.sql` | employees 扩 pending_task_count |
| 017 | `017_permission_rename.sql` | 权限表/列重命名（RENAME；含 `identity_invites.capabilities → permissions`） |
| 018 | `018_roles_and_skills.sql` | agent_roles / employee_capabilities / employee_role_bindings / position_role_bindings / position_employee_assignments / employee_contacts |
| 019 | `019_create_wf_nodes.sql` | wf_nodes + 旧版本自动补 `start`、旧节点 seq=order+1、坐标 x=(order+1)*240 |
| 020 | `020_create_wf_transitions.sql` | wf_node_transitions（旧线性数据生成 seq 顺序边） |
| 021 | `021_create_task_runs.sql` | task_node_runs + task_nodes.current_run_id + 旧任务回填 |
| 022 | `022_create_task_variables.sql` | task_variables |
| 023 | `023_create_artifacts.sql` | task_node_artifacts / task_node_artifact_edits |
| 024 | `024_create_escalations.sql` | task_escalations + org_teams.leader_employee_id |
| 025 | `025_skills_provides_capabilities.sql` | skills_packages.provides_capabilities |
| 026 | `026_task_loop_counters.sql` | task_tasks.loop_counters |
| 027 | `027_archive_fields.sql` | task_tasks.archived_at；保留天数走 `MAILBUS_TASK_ARCHIVE_DAYS`（默认 30） |
| 028 | `028_escalation_level.sql` | task_escalations.level |
| 029 | `029_agent_token_rotation.sql` | agents.endpoint_token_prev / prev_expires_at |
| 030 | `030_task_termination_reason.sql` | task_tasks.termination_reason（no_matching_branch / auto_terminated / manual） |
| 031 | `031_message_task_link.sql` | msg_messages.task_id + 索引 |
| 032 | `032_agent_registration_invites.sql` | agent_registration_invites 邀请码自助注册 |
| 033 | `033_ops_alerts.sql` | ops_alerts + ops_alert_rules 告警与通知规则 |
| 034 | `034_final_contract_alignment.sql` | 重建 task_node_runs 唯一键并补 fanout_slot；wf_versions.revision；员工/Agent/wf_defs 软删除字段；Agent endpoint 审批字段；Agent 邀请 data_scope；真人邀请撤销字段；token 密文与 lookup digest 字段及索引 |
| 035 | `035_collab_screen_layout.sql` | collab_screens 增 `source`、`config_json`、`published_config_json`、`config_version`、`updated_at`；补在线清理与离线查询索引 |

> 013–033 的双端哈希一致与测试库验证仅代表旧基线；034、035 是本轮新增需求，**尚未实施、尚未验证**。Python/Java 必须同步提交同编号 SQL。旧明文 token 的密文迁移需由使用 `MAILBUS_TOKEN_ENCRYPTION_KEY` 的应用迁移步骤完成，不能用 SQL 假装已加密。

评审结论见 [migration-review.md](./migration-review.md)。Java 013/014 已补齐，013–033 双端共 21 个文件哈希一致；已在「生产库副本 + 全新库」上验证到 schema 33。

### 9.2 分阶段实施

以下仅表示实现顺序，不代表任一端可独立上线；Python、Java 与前端必须按同一契约和迁移版本同批发布，mock 仅用于开发并同步同一契约。

```
Phase 1  DB 迁移 + 新表（018 起零行为；017 为破坏性改名，必须与 Phase 2 同批上线，禁止单独部署）
Phase 2  权限重命名（Python 全量 + 契约 + 测试）
Phase 3  工作流引擎（DAG 流转 / 调度 / runs / 扇出 / 打回 / 条件规则）
Phase 4  A2a 单入口 + result / heartbeat 分发 + 落库
Phase 5  协同界面（两个 tab / 角色管理 / 绑定配置 / 升级处理）+ 工作流拖拽编辑器（前端 + DAG 校验/导入导出/clone API + 只读版本 diff）
Phase 6  大屏投影扩展
Phase 7  hermes 侧 skill/rule + HTTP 入口；6 个 Agent 补岗位、审批 endpoint、签发新 token 并逐一回归；全部就绪后一次切换，随后删除旧 adapter
Phase 8  Trae / Cursor / 豆包 / 元宝 接入
Phase 9  Java 同步实现（同一契约、同一迁移编号：新表 / DAG / A2a / MCP 4 工具 / 编辑器 API）
Phase 10 全量回归 + 清理
```

### 9.3 线上迁移注意

- `identity_capability_grants` 重命名只影响 mailbus 内部查询：6 个 Agent 的 token 存于 `identity_sessions` 且不过期，无需重启容器或重新登记；须停服迁移，详见 [permission-rename-impact.md](./permission-rename-impact.md)
- `wf_versions.nodes` 迁移到 `wf_nodes` 后旧字段置空，保留只读一版
- 6 个 hermes agent 在 Phase 7 准备期间仍走旧通道；每个先补岗位、完成 endpoint 审批、签发新 token 并回归收发。全部 6 个就绪后一次切换，再删除旧 transport，不长期保留双引擎；新 token 是 A2A 切换动作，不是 permission rename 导致
- Java 与 Python 共用同一批迁移 SQL 与同一份契约文件：Java 按相同编号顺序执行，不得改写；发布必须同迁移版本，禁止一端先上线

---

## 10. 验收标准

1. 迁移脚本在生产库可无错执行且数据不丢；`foreign_key_check` 与 `integrity_check` 通过
2. 能创建带分支 / 并行 / 打回 / 终验的 DAG 工作流并发布
3. 能配置岗位 → 角色 → 员工，管理员可覆盖指定
4. 启动任务后节点按流转自动派给正确员工（capability 交集匹配 + 负载最少）
5. completed → 自动推进；failed → 按 max_retries 换人；耗尽 → 转人工
6. 打回产生新 run，旧 result 可查，artifacts 只留最新
7. 扇出多 run 全部完成才推进，join 节点可汇总
8. 循环超限转人工，不静默死循环
9. 真人在协同界面两个 tab 看到对应待办并能推进
10. 审批超时 expired，干活超时升级通知，均留 escalation 记录
11. artifacts 权限仅任务参与者可读；外部 Agent 通过签发 URL 上传与读取（24h、单文件 ≤100MB）
12. 6 个 hermes agent 迁到 A2a 后收发正常
13. Python 与 Java 全量测试全绿；双端同一契约、同一迁移编号，核心路径回归一致
14. 拖拽编辑器能建图、校验（环/孤立节点/缺岗位）、导入导出、只读版本 diff，与 DB 结构一致；保存乐观锁冲突有明确处理路径
15. MCP 工具收敛为 4 个，Trae/Cursor 按新配置可用
16. token 手动轮转旧值 24h 可用；吊销即时失效并判在跑 run 失败
17. 一级升级 72h 无人处理自动终止任务；归档 30 天压缩、超管可解档
18. 大屏上节点状态正确投影到对应工位，并发时显示角标
19. 条件边全部未命中时任务自动终止 `cancelled` 并记录 `termination_reason = no_matching_branch`，大屏与工单可展示原因
20. 真人共享待办先到先得：多人同时认领只有一个成功，其余人列表实时移除
21. 审批或签：任一审批人处理即生效，其余待办关闭；超时不自动通过
22. 定时触发错过补跑一次，同一工作流不产生并发运行实例
23. 外壳离线宽限 90s 后仍未恢复，在跑 run 判失败并重派；宽限期内恢复不受影响；注册记录不因离线自动删除
24. 消息触发只响应显式 command 指令，聊天/广播不触发，重复 message_id 不重复建任务
25. 迟到结果返回 409 且不改变状态；重复结果幂等返回 200，节点只推进一次
26. MCP 旧工具调用返回 404，新 4 工具按新配置可用
27. 发起人与超管可取消任务；在跑 run 尽量收到 `task_cancel`，取消立即生效
28. 外部 Agent 过期 URL 上传被拒；内联产物超限返回 413；正常上传后产物可被参与者读取
29. 本人任务创建后立即启动；指定他人无 `task_dispatch` 返回 403；自由任务通过一个虚拟节点/run 完成，无草稿页和直接状态推进入口
30. 扇出同节点同 attempt 的多个分片可共存；普通节点 `fanout_slot=0`，分片独立重试且唯一键无冲突
31. 普通节点多个前向入边发布报 `E_MULTI_IN_REQUIRES_JOIN`；显式 `parallel_join` 可汇聚，回边不计入限制
32. missing 分片人工补完不自动推进；发起人或超管重跑 join 后生成新 join attempt/下游 run、审计与范围展示
33. 终验零回边驳回落 `approval_rejected`，一回边驳回进入重做，多条回边发布报错；普通 `approval` 不可创建
34. 邀请人越权授予权限或扩大 data_scope 被后端拒绝；注册时按当前授权上界再次校验
35. endpoint 变更后未经管理员审批不派新任务；SSRF、DNS 和可信网段校验通过后才可恢复投递
36. 当前/旧 token 密文可由配置密钥解密用于出站，lookup digest 可完成入站反查；数据库、日志和界面均不出现明文
37. self/team/global 对任务、消息、产物、指标和 CSV 使用同一服务端参与者口径
38. 员工、Agent、工作流删除为软删除/停用，有活跃 run 返回 409，历史详情仍可读取；任务无物理删除入口
39. 真人邀请过期/已使用访问返回 410，重发作废旧链接；Agent 邀请仍按不存在 404、已使用 409、撤销/过期 410
40. 告警只对进入 firing 通知，同规则同资源按 `silence_seconds` 冷却；恢复不通知，webhook/邮件最终失败有审计
41. Graph 保存以整数 `revision` 检测冲突，强制覆盖写审计；列表包装、UTC 时间和新组织路径在 Python/Java/前端一致
42. `/twin` 匿名打开自动登记屏幕，`/console/collab` 可接管命名、绑定团队与清理；两端共用 `collab_screens`，管理端不手工新建屏幕
43. `/twin` 默认匿名 kiosk 不显示侧栏、名册、工位抽屉和页脚；登录交互模式按本人权限发起任务，空闲 5 分钟退回 kiosk；公开投影不返回 `employee_id/agent_id/team_id/endpoint/token`；绑定团队后其他工位留空
44. `office/grid/custom` 三布局可用；`grid` 未绑定团队保存 422；`custom` 可视化编辑保存后与发布效果一致；分辨率两档只影响预览比例
45. 心跳 30 秒、60 秒判离线；在线删除 409；发布使 `config_version+1` 且 30 秒内生效；`paused` 仅停止应用新配置，任务/消息/结对实时数据继续更新；只清理未接管的自动屏
46. 定向聚焦只作用于目标屏幕；公开登记 429、公开 SSE 503 与断线退避可验证；`auto` 主题跨 19:00/06:00 自动切换
47. 工位按新任务状态映射，扇出分片计入「并发 N」；气泡只显示结对与派单摘要，正文截断且不含附件、payload
48. 关闭浏览器或设备重启后，凭 `localStorage` 中的 `screen_id/secret` 继续心跳且接管配置保留；本地记录丢失则登记为新屏，不覆盖旧屏配置
49. 登记响应返回的 `secret` 可完成心跳；库内与列表只出现哈希/指纹，接口无法二次回显；交互模式只展示屏幕绑定团队与本人 `data_scope` 的交集

---

## 11. 补充定义（原待定 7 项已定案）

### 11.1 token 轮转与吊销

| 操作 | 行为 |
|---|---|
| 轮转 | 生成新 token；当前/旧值均加密落库，旧 token 的 lookup digest 写入 `endpoint_token_prev_lookup_hash`，24h 内仍可用；到期清空密文与 digest |
| 吊销 | 当前/旧 token 密文与 lookup digest 立即清空，外壳标 offline，在跑 run 立即判失败并进入重派/转人工 |
| 重签 | 新 token 明文仅在签发/轮转响应返回一次；mailbus 出站时从密文解密，日志和界面只显示指纹 |

### 11.2 file_bus 格式

写出文件内容 = A2a HTTP payload（同一 JSON schema）。建议路径 `file_bus/outbox/<employee_id>/<message_id>.json`，Agent 处理后写 `file_bus/inbox/<employee_id>/<message_id>.result.json`，格式同 result 结构。Agent 侧一套序列化代码即可支持两种通道。

### 11.3 MCP 工具集（收敛为 4 个）

| 工具 | 端点映射 |
|---|---|
| `mailbus_inbox` | 拉取待办（对应 `/api/mcp/pull`） |
| `mailbus_send` | 发消息 |
| `mailbus_ack` | 确认受理 |
| `mailbus_result` | 回推节点结果 |

删除 `task_create` / `task_fsm` / `step_result` 等 12 个（工作流由引擎驱动，Agent 不再自建任务）。需同步更新 `shared/contracts/mcp-tools-v0.json`，并通知现有 Trae/Cursor 配置。

**切换方式：直接切换**，不做双版本过渡。上线即只暴露 4 个工具，旧工具调用返回 404；发布前完成契约文件、文档与示例配置更新，并在管理页公告「MCP 工具已变更」。旧配置持有者需按新文档重新注册。Java 侧同步实现同样的 4 个工具与注册流程。

### 11.4 工作流可视化编辑器

- 本侧实现：前端拖拽（节点/连线/条件配置）+ 后端 DAG 校验与导入导出 API
- 后端提供：`POST /api/workflows/{id}/versions/{v}/validate`（环检测、孤立节点、缺失 position、条件语法校验）、`GET/PUT .../graph`（JSON 导入导出）、`POST .../clone`（已发布版本派生草稿）
- 编辑器与 `wf_nodes` / `wf_node_transitions` 一一对应，不引入额外存储格式；新增 `pos_x` / `pos_y` 两个坐标列（migration 019）
- 已发布版本只读，修改走「派生草稿」（`latest_version + 1`，已有草稿时先提示切换或新建）；版本 diff 由前端计算，不新增后端端点
- 新增前端依赖：`@xyflow/react`（画布）、`@uiw/react-codemirror` + `@codemirror/lang-json`（条件 JSON 编辑，懒加载，暗色主题内联定制）
- 交互细节（三栏布局、6 类节点、连线规则、属性面板字段、条件构建器、扇出开关、校验错误码、保存/发布/离开提醒、只读 diff、快捷键、前端组件落点）见 [workflow-editor-ux.md](./workflow-editor-ux.md)

### 11.5 二级升级兜底

- 一级升级（团队负责人 + 超管）超过**二级阈值**（默认 72h，可配）无人处理 → 任务自动终止 `CANCELLED`，`termination_reason = auto_terminated`
- `task_escalations` 增加 `level` 字段（1 / 2），二级结束写 `resolution = auto_terminated`
- 大屏与工单展示终止原因

### 11.6 归档与解档

- 归档：任务完成 30 天后压缩为 `<task_id>.tar.gz`，`task_tasks.archived_at` 置位
- 解档：仅超管可操作；解档到临时目录 `<data_dir>/workspaces/_restored/<task_id>/`，7 天后自动清理
- 解档期间产物只读

### 11.7 大屏映射

- 节点 → 工位：默认取该节点当前 `assigned_employee_id` 的 `seat_id`
- 若节点未分配或需固定展示位，在 `wf_nodes.config` 写 `{"seat_id": "..."}` 覆盖
- 任务状态：`pending / running / blocked / done / cancelled / failed`
- 工位视觉状态：`idle`（无活跃 run）/ `running`（存在 pending/running run）/ `waiting_human`（待认领、待提交或待审批）/ `failed`（失败且无补偿进行中）/ `done`（活跃 run 全部完成）
- 多节点或扇出分片映射到同一工位时，工位显示「并发 N」角标；N 为该工位活跃 run 数
- 屏幕绑定团队后，只渲染该团队成员；其他工位留空，不显示姓名与任务
- 公开投影字段白名单见 7.5；任务附件、payload、内部 ID 不上屏

### 11.8 告警与通知

```sql
CREATE TABLE ops_alert_rules (
  rule_id        TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  alert_type     TEXT NOT NULL,          -- agent_offline / run_timeout / escalation_backlog / outbox_backlog / workflow_failure_rate
  threshold      REAL,
  channel        TEXT NOT NULL,          -- webhook / email / inapp
  target         TEXT,                   -- webhook URL / 邮箱 / 员工 ID
  silence_seconds INTEGER NOT NULL DEFAULT 300,
  enabled        INTEGER NOT NULL DEFAULT 1,
  created_by     TEXT,
  created_at     REAL NOT NULL
);

CREATE TABLE ops_alerts (
  alert_id       TEXT PRIMARY KEY,
  rule_id        TEXT,
  type           TEXT NOT NULL,
  severity       TEXT NOT NULL,          -- info / warn / critical
  resource_type  TEXT,
  resource_id    TEXT,
  status         TEXT NOT NULL,          -- firing / acked / resolved
  value          TEXT,
  threshold      TEXT,
  first_seen_at  REAL NOT NULL,
  last_seen_at   REAL NOT NULL,
  acked_by       TEXT,
  acked_at       REAL,
  resolved_at    REAL
);
CREATE INDEX idx_ops_alerts_status ON ops_alerts (status, last_seen_at);
```

- APScheduler 每 60s 评估一次；同一规则、同一资源在 firing 期间去重，恢复只自动置 `resolved`，**不发送恢复通知**
- 仅在进入 firing 时发送通知；`silence_seconds` 是**同一规则、同一资源两次通知之间的冷却秒数**，不是每日静默时段；冷却不延后恢复状态更新
- webhook / 邮件单次请求超时 5 秒，失败后指数退避重试 3 次；最终失败写审计。支持 webhook / 邮件 / 站内
- 预置规则：Agent 离线 >5 分钟、run 超时、升级待处理 >1 小时、outbox 积压 >100、工作流失败率 >20%（1 小时）

---

## 12. 本轮补充确认（2026-11-24）

| # | 议题 | 结论 |
|---|---|---|
| E1 | 扇出互斥 | 扇出节点只能 1 条出边，与多出边/条件分支互斥（`E_FANOUT_WITH_MULTI_OUT`） |
| E2 | 多出边 | 出边 ≥2 时禁止条件边与无条件边混合（`E_MIXED_OUT_EDGES`） |
| E3 | 条件未命中 | 全部条件边未命中 → 任务自动终止，`termination_reason = no_matching_branch` |
| E4 | 真人派工 | 共享待办、先到先得（CAS 认领）；`config.assignee_id` 可收窄为单人 |
| E5 | 审批 | 或签：任一审批人通过即生效、任一否决即打回；超时 `expired` 不自动通过 |
| E6 | 定时触发 | cron 5 段、Asia/Shanghai；错过 1h 内补跑一次；同一工作流单实例 |
| E7 | 离线处理 | 判离线后宽限 90s；仍离线则在跑 run 失败并按 `max_retries` 重派；注册记录不自动删除 |
| E8 | 编辑器 | 见 [workflow-editor-ux.md](./workflow-editor-ux.md) 第 17 节（含派生草稿、diff 前端计算、CodeMirror 6） |
| E9 | 消息触发 | 仅 `kind=command` 且带 `workflow_id` 的指令消息、已注册发送者；`message_id` 幂等 |
| E10 | 结果幂等 | 按 `run_id + attempt_no` 严格校验；stale → 409 + 审计；重复 → 200 不重复推进 |
| E11 | MCP 过渡 | 直接切换到 4 个工具，不做双版本；旧工具 404，发布前更新契约/文档/示例配置 |
| E12 | 任务取消 | 发起人 + 超管；未完成 run 置 skipped，在跑 run 尽力发 `task_cancel` |
| E13 | 外部产物 | 签发一次性 PUT URL（24h、单文件 ≤100MB、用后即废）；≤5MB 可在 result 内联 base64 |
| E14 | Java 范围 | 本期与 Python **全量同步实现**，同契约、同迁移编号，不允许语义分叉 |
| E15 | 迁移评审 | 旧版本自动补 start；归档走环境变量；021 完整回填；新表时间戳统一 REAL；Java 先补 013/014 — 见 [migration-review.md](./migration-review.md) |
| E16 | 后端收尾 | 扇出不足等凑齐、超时降级；join 不阻塞并标记缺失；msg_messages 回链 task_id；Agent 邀请码自助注册；人工节点必填结果；待办计数引擎维护+启动校准；下载 URL 24h；循环仅回边 +1 |
| E17 | 前端收尾 | 新增 ops_alerts / ops_alert_rules（033），60s 检测、去重、同规则同资源通知冷却，webhook/邮件/站内通知；恢复不发通知 |

待定项已清零（2026-11-24）。

### 12.1 孪生与协同大屏补充（2026-11-25）

| # | 议题 | 结论 |
|---|---|---|
| T1 | 屏幕身份 | `/twin` 自动登记，`screen_id/secret` 存设备 `localStorage` 跨重启复用；`/console/collab` 接管；两端共用 `collab_screens`，管理端不手工新建 |
| T2 | 访问形态 | `/twin` 默认匿名 kiosk；登录员工可切交互模式并发起任务，空闲 5 分钟自动退回 kiosk |
| T3 | 公开字段 | 姓名、岗位、Agent 名、任务、节点、进度、`seat_id`、结对与气泡；不返回员工/Agent/团队/endpoint/token 等内部标识 |
| T4 | 任务粒度 | 新任务状态 + 同工位「并发 N」角标，扇出分片计入 |
| T5 | 布局 | `office/grid/custom` 三模式；`grid` 自动生成且必须绑定团队；`custom` 控制台可视化编辑；分辨率两档 |
| T6 | 主题 | 配置 `dark/light` 优先，`auto` 按本地时间 19:00–06:00 |
| T7 | 气泡 | 结对消息 + `task_assignment` 摘要；每条结对最新 1 条，缓冲 3 条，正文截断 |
| T8 | 聚焦 | 仅定向投送单块屏幕；一次性指令，其他屏幕不跟随 |
| T9 | 发布 | 草稿/已发布分离，发布递增 `config_version`，30 秒内生效；暂停仅停新配置，实时数据继续 |
| T10 | 生命周期 | 心跳 30 秒、60 秒离线；仅离线可删；只清理未接管的自动屏；登记 429、SSE 503 |
| T11 | 密钥存储 | 服务端只存不可逆哈希，明文仅登记响应返回一次；轮换=删除后重新登记并重新下发 |
| T12 | 交互取数 | 屏幕绑定团队与本人 `data_scope` 取交集；未绑定团队时按本人范围 |

待定项已清零（2026-11-25）；接入模板见 [agent-onboarding-template.md](./agent-onboarding-template.md)。

---

## 13. 最终跨端契约与生命周期（冻结基线）

### 13.1 HTTP、时间与选项接口

- 组织管理路径统一为 `/api/employees`、`/api/positions`、`/api/teams`；Python、Java、前端和 mock 只实现这一套，不保留旧路径运行时回退
- JSON 请求/响应中的时间统一 ISO 8601 UTC（如 `2026-11-24T14:02:11Z`）；SQLite 继续使用 REAL epoch 秒，由适配层转换，不得把两种表示混用
- 分页列表统一 `{items,total,limit,offset}`；空列表返回 `items=[]`、`total=0`，不直接返回裸数组
- 错误结构继续沿用 `{error,error_code,message_zh}`，本轮不另起错误格式
- 编辑器和任务表单使用登录可读的脱敏选项接口，而不是完整组织管理接口：
  - `GET /api/options/employees?position_id=&limit=&offset=`：仅返回 `employee_id/display_name/position_id/team_id/agent_id/enabled` 等选项所需字段
  - `GET /api/options/positions?limit=&offset=`：仅返回 `position_id/name/enabled`
- 选项接口不返回登录名、联系方式、权限、token、审计信息；仍按当前用户可分配范围过滤，服务端不得因为“登录即可读”而开放完整员工档案
- Graph 乐观锁统一为 `revision`：GET 返回整数，PUT body 为 `{graph,revision}`，成功保存后 revision +1；`?force=true` 保留覆盖保存语义，写审计并记录基准 revision，不再使用 `expected_updated_at`

### 13.2 任务创建、自由任务与 join 重跑

- `POST /api/tasks` 创建本人任务并立即启动需要 `task_create`；省略 `owner_id` 或 `owner_id=本人` 均属本人任务。指定他人或代派必须同时有 `task_dispatch`
- 新版不单独暴露草稿任务页，也不提供 `/advance` 或任意修改任务状态的入口。已发布工作流由引擎推进，自由任务由唯一 run 的 result 推进
- 自由任务在运行库中包装为一个虚拟执行节点和一个 run，但不新增第七种 `wf_nodes.node_type`：真人走共享待办认领/提交结果，Agent 走 A2A result；run done 后任务 done
- 任务创建响应返回完整任务及首个 run；前端创建成功直接进入任务详情，不再显示“草稿 → 派发 → 推进”旧操作链
- join 显式重跑：`POST /api/tasks/{task_id}/nodes/{node_id}/rerun-join`，body 带 `fanout_group`；仅发起人或超管可用。服务端校验补完分片后创建新 join attempt 和下游 run，写审计并返回本次重跑范围

### 13.3 真人邀请

- `POST /api/employees/invite` 创建默认 24h 有效、一次性、可撤销的真人邀请链接；创建/重发均执行 6.4 的授权上界校验
- 访问不存在链接返回 404；已撤销、已过期或已使用的链接访问返回 410。Agent 邀请码的“已使用 409”规则不套用到真人链接
- 重发不是延长旧链接：同事务作废旧邀请并生成新 token/链接，旧链接立即返回 410
- 注册时按邀请快照写入岗位和权限，同时再次检查邀请人当前权限、data_scope、启用状态及邀请有效期；注册成功后原子标记 used，重放返回 410

### 13.4 软删除与停用

- 员工移除、Agent 注销、工作流删除分别写 `identity_employees.deleted_at/deleted_by`、`agents.deleted_at/deleted_by`、`wf_defs.deleted_at/deleted_by`，默认列表排除，历史任务与审计继续可读
- 任一资源存在活跃 run 时返回 409，不执行删除；前端展示冲突数量和处理建议，不自动取消任务
- 员工或 Agent 停用成功后立即退出候选池，并撤销其会话、当前/旧 token；工作流停用后不可创建新任务，运行中任务因前置 409 不受影响
- 任务前台只提供取消，不提供物理删除；归档与超管解档沿用 11.6，不等于物理删除

### 13.5 大屏与孪生

- `/twin` 默认匿名只读 kiosk，不要求登录；登录员工可切交互模式，按本人权限取数（屏幕绑定团队 ∩ 本人 `data_scope`）并发起任务，空闲 5 分钟自动退回 kiosk。首次打开自动登记屏幕并取得一次性屏幕密钥（服务端只存哈希），设备写入 `localStorage` 跨重启复用，心跳与离线上报携带 `X-Screen-Secret`；`/console/collab` 通过同一 `collab_screens` 表接管命名、绑定团队、布局与清理，不提供手工新建屏幕
- `?preview=1` 只读预览不登记、不发心跳、不接收聚焦；`screen_id` 与密钥不匹配时按新屏登记，绝不覆盖已有配置
- 屏幕配置分草稿 `config_json` 与已发布 `published_config_json`；保存只写草稿，发布快照并递增 `config_version`，`/twin` 只读已发布配置
- 布局支持 `office/grid/custom`：`grid` 按绑定团队自动生成且必须绑定团队；`custom` 由控制台可视化编辑器产出布局 JSON；`office` 复用现有办公室布局
- 分辨率仅 1920×1080 / 3840×2160 两档，只影响预览比例；主题 `auto/dark/light`，`auto` 按本地时间 19:00–06:00 切换
- 心跳 30 秒、60 秒判离线；仅离线屏幕可删除，在线删除 409；仅清理从未被管理端接管且离线超过 30 天的自动登记屏幕；公开登记按 IP 限速 10 次/分钟返回 429，在线自动屏超 64 台返回 503，公开 SSE 满返回 503；`paused` 仅停止应用新配置，实时数据继续
- 公开投影只返回姓名、岗位、Agent 名、任务、节点、进度、`seat_id`、结对与气泡；不返回 `employee_id / agent_id / team_id / endpoint / token / created_by`；公开配置只返回 `team_bound`，团队过滤在服务端完成，绑定团队后其他工位留空
- 任务状态 `pending/running/blocked/done/cancelled/failed`，工位视觉 `idle/running/waiting_human/failed/done`；同一工位多个活跃 run 或扇出分片显示「并发 N」
- 气泡合并同层结对消息与 `task_assignment` 摘要，每条结对只显示最新 1 条，前端最多缓冲 3 条，正文截断 40 字，不展示附件与 payload
- 远程聚焦 `POST /api/collab/screens/{id}/focus` 只作用于目标屏幕，一次性指令不改配置；同浏览器其他标签继续本地同步，其他屏幕不跟随

### 13.6 实施边界

本节及 F1–F21 是 Python、Java、前端和 mock 的共同实施基线。文档回写不代表这些能力已经落地；实现时必须同步更新共享 OpenAPI/契约、迁移和双端测试，不允许单侧先行改变线上语义。
