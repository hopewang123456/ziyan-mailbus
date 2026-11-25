# 前端需求澄清

> 2026-11-25 · v1.2 全量改版（直接替换旧控制台，孪生与协同大屏口径已冻结）
> 配套：[agent-unification-design.md](./agent-unification-design.md)、[workflow-editor-ux.md](./workflow-editor-ux.md)

---

## 1. 信息架构与页面范围（已确认）

### 1.1 导航结构

左侧分组侧栏，5 个分组；分组标题不可点击，组内按页面排列。桌面优先（≥1280），最小支持 1024，本期不做移动端。

| 分组 | 页面 | 路由 | 状态 |
|---|---|---|---|
| 工作台 | 概览 | `/console` | 改版 |
| 工作台 | 指标与报表 | `/console/metrics` | 改版 |
| 协作 | 任务中心（全部 / 我的工作 / 审批） | `/console/tasks?tab=all\|mine\|approvals` | 合并改版 |
| 协作 | 消息与追迹 | `/console/messages` | 改版 |
| 协作 | 协同大屏 | `/console/collab` | 改版（原协同管理） |
| 组织 | 组织（员工 / 岗位 / 角色 / 团队） | `/console/organization?tab=staff\|positions\|roles\|teams` | 新建 |
| 流程 | 工作流模板 | `/console/workflows` | 改版 |
| 流程 | 工作流版本 | `/console/workflows/:id` | 新建 |
| 流程 | 工作流编辑器 | `/console/workflows/:id/versions/:v/editor` | 新建（整页全宽，见交互稿） |
| 流程 | 技能包 | `/console/skills` | 改版 |
| 系统 | Agent 与接入（外壳 / 邀请码） | `/console/agents?tab=shells\|invites` | 改版 |
| 系统 | 集成 | `/console/integrations` | 改版 |
| 系统 | 审计与告警 | `/console/audit` | 改版 |
| 系统 | 设置向导 | `/console/setup` | 改版 |

### 1.2 合并与重定向

- 原「员工与入伙」「团队与工位」并入组织页对应 Tab
- 原「审批中心」并入任务中心 Tab
- 旧地址保留 301 式前端重定向，避免书签失效：
  - `/console/staff` → `/console/organization?tab=staff`
  - `/console/teams` → `/console/organization?tab=teams`
  - `/console/approvals` → `/console/tasks?tab=approvals`
- 大屏 `/twin` 不在控制台导航内，保持在独立入口

### 1.3 导航可见性

- 分组标题在组内**至少一个页面可见**时显示，否则整组隐藏
- 页面级可见性沿用「权限 → `can()`」模式，具体权限点在第 2 项权限矩阵中定稿
- 组织、系统两组的默认可见权限更严格（管理类），普通员工只看到工作台、协作中的任务/消息

### 1.4 本期范围

- 全量改版：上表 13 个页面全部按新设计系统重做，直接替换旧控制台
- `/twin` 展示端与 `/console/collab` 同批重做：默认匿名 kiosk、登录后交互模式、三种布局、草稿/发布、定向聚焦与公开投影白名单；不计入控制台 13 页导航
- 不做新旧双导航、不做分批灰度；旧页面代码删除
- 后端未就绪的页面允许先接 mock，但发布前必须切真实接口

### 1.5 权限与角标

- 每个页面/按钮的权限点见第 2 节
- 导航角标：我的待办 = 我可认领 + 我已认领未完成；审批 = 待我处理（`hitl_resolve` 可见时）
- 角标随 `/api/tasks/summary` 拉取，进入页面与任务事件推送时刷新，不轮询

---

## 2. 角色与权限矩阵（已确认）

### 2.1 模型

- **不新建登录角色表**：权限仍按员工逐项授予（`identity_permission_grants`），前端提供 4 个预设模板一键套用，套用后可微调
- 模板只是前端常量，后端仍按权限点校验；不引入 `permission_roles`
- `agent_roles` 是**业务角色**（决定会做什么），不参与登录鉴权；员工可以没有任何业务角色，但仍能登录
- `console_admin` 等价 `*`；超管只授这一个权限
- `data_scope`（self / team / global）与权限正交，单独设置
- 真人/Agent 邀请均只能授予邀请人当前有效权限的子集，data_scope 不得超过自身；`console_admin`、`*`、`global` 仅超管可授。前端过滤可选项，后端在创建、重发和注册时强制复核

### 2.2 权限清单（21 个）

| 分组 | 权限 | 用途 |
|---|---|---|
| 协作 | `message_read` | 读消息 |
| 协作 | `message_send` | 发消息 |
| 协作 | `task_create` | 创建任务 |
| 协作 | `task_dispatch` | 派发任务 |
| 协作 | `result_submit` | 提交节点结果 |
| 协作 | `hitl_request` | 发起人工介入 |
| 协作 | `hitl_resolve` | 处理审批/人工介入 |
| 流程 | `workflow_create` | 新建工作流 |
| 流程 | `workflow_modify` | 编辑草稿/派生版本 |
| 流程 | `workflow_publish` | 发布版本（新增） |
| 组织 | `employee_invite` | 邀请真人 |
| 组织 | `employee_remove` | 移除员工 |
| 组织 | `org_manage` | 岗位/团队/工位管理 |
| 组织 | `role_manage` | 业务角色 CRUD（新增） |
| 组织 | `role_bind` | 岗位/员工绑定角色（新增） |
| 组织 | `agent_deregister` | 注销 Agent 外壳 |
| 运维 | `log_read` | 审计日志 |
| 运维 | `system_config` | 集成/设置/技能包 |
| 运维 | `console_admin` | 控制台超管（等价 `*`） |
| 运维 | `escalation_resolve` | 处理超时升级（新增） |
| 运维 | `artifact_read_all` | 读取任意任务产物（新增） |

取消任务不新增权限：发起人本人或 `console_admin` 可取消。

### 2.3 预设模板

| 权限 | 主管 | 员工 | 只读 |
|---|---|---|---|
| `message_read` | ✓ | ✓ | ✓ |
| `message_send` | ✓ | ✓ | — |
| `task_create` | ✓ | ✓ | — |
| `task_dispatch` | ✓ | — | — |
| `result_submit` | ✓ | ✓ | — |
| `hitl_request` | ✓ | ✓ | — |
| `hitl_resolve` | ✓ | — | — |
| `workflow_create` | ✓ | — | — |
| `workflow_modify` | ✓ | — | — |
| `workflow_publish` | — | — | — |
| `role_bind` | ✓ | — | — |
| `escalation_resolve` | ✓ | — | — |
| `artifact_read_all` | ✓ | — | — |
| 其余管理/运维权限 | — | — | — |

- **超管**：只授 `console_admin`
- **主管**：上表主管列，`data_scope = team`
- **员工**：协作最小集，`data_scope = self`
- **只读**：仅 `message_read`，`data_scope = self`

新建真人默认套用「员工」模板；`workflow_publish`、邀请码、集成、设置默认只有超管有。

### 2.4 页面可见性

| 页面 | 可见条件 |
|---|---|
| 概览 | 登录即可 |
| 指标与报表 | 登录即可（数据按 `data_scope` 过滤） |
| 任务中心 · 全部/我的工作 | 登录即可 |
| 任务中心 · 审批 | `hitl_resolve` |
| 消息与追迹 | `message_read` |
| 协同大屏 | `console_admin` |
| 组织 · 员工 | `org_manage` 或 `employee_invite` |
| 组织 · 岗位 | `org_manage` |
| 组织 · 角色 | `role_manage` |
| 组织 · 团队 | `org_manage` |
| 工作流模板 | 登录即可查看；按钮按 2.5 |
| 工作流编辑器 | `workflow_modify` |
| 技能包 | `system_config` |
| Agent 与接入 · 外壳 | `org_manage` 或 `agent_deregister` |
| Agent 与接入 · 邀请码 | `console_admin` |
| 集成 | `system_config` |
| 审计与告警 | `log_read` |
| 设置向导 | `system_config` |

空组隐藏；组内页面全部不可见时整组不渲染。

### 2.5 按钮级

| 页面 | 按钮 | 条件 |
|---|---|---|
| 任务中心 | 新建本人任务 | `task_create` |
| 任务中心 | 指定他人/代派 | `task_create` + `task_dispatch` |
| 任务中心 | 认领 | 同岗位候选人，无额外权限 |
| 任务中心 | 提交结果/产物 | `result_submit` 且为当前 run 执行人 |
| 任务中心 | 取消任务 | 发起人或 `console_admin` |
| 任务中心 | 审批通过/驳回 | `hitl_resolve` |
| 任务中心 | 处理升级 | `escalation_resolve` |
| 任务中心 | 下载他人产物 | `artifact_read_all` |
| 工作流 | 新建 | `workflow_create` |
| 工作流 | 编辑/保存/派生 | `workflow_modify` |
| 工作流 | 发布 | `workflow_publish` |
| 工作流 | 删除 | `workflow_modify` |
| 组织 | 邀请真人 | `employee_invite` |
| 组织 | 移除员工 | `employee_remove` |
| 组织 | 岗位/团队/工位增删改 | `org_manage` |
| 组织 | 角色增删改 | `role_manage` |
| 组织 | 绑定角色/技能 | `role_bind` |
| Agent | 生成邀请码 | `console_admin` |
| Agent | 轮转/吊销 token | `console_admin` 或 `agent_deregister` |
| 消息 | 发送 | `message_send` |

### 2.6 行为约定

- 权限变更下一次请求生效，不强制退出登录
- 列表数据范围由服务端按 `data_scope` 过滤，前端不做二次裁剪：`self` 为本人发起或曾参与 run/审批；`team` 为本团队任一参与者相关；`global` 为全部。消息按收发双方，产物继承任务，指标/CSV 使用同一过滤结果
- 无权限的按钮不渲染（不是置灰），避免暴露操作语义
- 只读模板只展示页面与数据，不显示任何提交类按钮
- 现有 6 个 Agent 的 3 项权限（read/send/result_submit）保持不变

### 2.7 后端跟进

- 权限枚举从 16 增至 21，契约与 Java 同步
- 新真人默认授予协作最小集
- `can()` 字段名随 `capabilities → permissions` 调整，值不变

---

## 3. 任务中心与我的工作（已确认）

### 3.1 路由与 Tab

```
/console/tasks?tab=all        全部任务
/console/tasks?tab=mine       我的工作
/console/tasks?tab=approvals  审批
/console/tasks/:id            任务详情（独立页）
```

- 三个 Tab 共用顶部筛选与右侧角标
- 角标：我的工作 = 可认领 + 已认领未完成；审批 = 待我处理
- 审批 Tab 无 `hitl_resolve` 时不渲染，URL 直达返回 403 空态

#### 创建与启动

- 「新建任务」支持**自由任务**和**已发布工作流**；不创建或展示独立草稿任务页
- `POST /api/tasks` 省略 `owner_id` 或设为本人时，只需 `task_create`，创建后**立即启动**并进入任务详情；指定他人或代派必须同时有 `task_dispatch`
- 自由任务由一个虚拟执行节点和一个 run 承载：真人认领并提交结果，Agent 通过 A2A result 回传；run 完成后任务 done
- 不提供旧 `/advance`、直接修改任务状态或“草稿 → 派发 → 推进”操作链；工作流任务只由引擎和 result 推进
- 创建响应返回完整任务与首个 run；前端不得按裸数组或旧 draft DTO 推测状态

### 3.2 列表

列：标题 / 状态 / 当前节点 / 负责人 / 进度 / 更新时间。

- 筛选：关键词、状态多选、工作流、负责人、时间范围
- 默认排序：更新时间倒序
- 点击行进入详情页，不做行内展开
- 状态标签与后端一致：pending / running / blocked / done / cancelled / failed
- 取消任务在详情页头部显示终止原因（`no_matching_branch` / `auto_terminated` / `manual` / `approval_rejected`）

### 3.3 我的工作

分三块：

1. **可认领（共享待办）**：按岗位候选人匹配，显示任务、当前节点、预计耗时、发起人；每行「认领」按钮
2. **我已认领**：状态 running，显示截止时间与「提交结果」入口
3. **待我补充**：失败转人工的 run，显示失败原因与「重新提交」

认领流程：

- 点击认领 → `POST /api/tasks/{task_id}/nodes/{node_id}/claim`
- CAS 成功：行移入「我已认领」，Toast「认领成功」
- 409：Toast「已被他人认领」并刷新列表
- 无候选人资格：按钮不渲染

### 3.4 任务详情页

```
┌──────────────────────────────────────────────────────────────┐
│ 标题  状态Tag  工作流 v3  发起人  更新时间     [取消任务]      │
├───────────────────────────────┬──────────────────────────────┤
│ 节点时间线                     │ 当前操作卡片（粘性）          │
│ ● start                       │ 节点：执行分析               │
│ ● 收集资料  done  agent 灵昭   │ 执行人：我                   │
│   result 摘要 / 产物 2         │ [提交结果]                   │
│ ◉ 执行分析  running  human 我  │                              │
│ ○ 汇总      pending            │ ─────────────────────────    │
│                               │ 概览 / 变量 / 产物 / 事件     │
└───────────────────────────────┴──────────────────────────────┘
```

- 左栏节点时间线：节点名、类型、状态、执行人、attempt、结果摘要、产物数；点击节点切换右栏
- 扇出节点按 `fanout_group + fanout_slot` 展示各分片及独立 attempt；普通节点 `fanout_slot=0` 无需显示槽位，不能只用 `current_run_id` 判断扇出活跃分片
- `parallel_join` 展示前驱终态、完成分片与 missing 分片；人工补完后不自动重跑。发起人或超管可见「重跑汇聚」，确认范围后调用 rerun-join，展示新 join attempt、下游 run 和审计记录
- 右栏当前操作卡片：仅当当前 run 属于我且状态 running 时显示提交入口
- 概览：任务元信息、变量快照、当前 run 的 deadline/升级状态
- 变量：`task_variables` 表格，来源标记 input/system
- 产物：文件列表，支持图片/文本/PDF 内联预览，其他类型下载
- 事件：`task.updated` / `artifact.updated` 等时间线，只读
- 取消：发起人或超管可见；二次确认，取消后展示终止原因

### 3.5 提交结果

- 弹窗内：结果文本框（Markdown / JSON 模式切换）+ 拖拽上传产物
- 结果必填；JSON 模式先本地解析校验，失败不提交
- 产物单文件 ≤100MB，可多选；上传中禁用提交
- 提交 → `POST /api/tasks/{id}/nodes/{node_id}/result`，带 `attempt_no`
- 409（stale attempt）：提示「该节点已被重新指派」并刷新详情
- 成功后关闭弹窗，节点变 done，右栏切到下一节点

### 3.6 审批

- 审批 Tab 列表：标题、类型、发起人、等待时长、状态
- 点击进入任务详情，右栏显示审批卡片：申请内容、变量、历史意见
- 操作：通过（意见可选）/ 驳回（意见必填）
- 本期审批只对应 `final_approval`；中间复核是 `human + condition`，出现在我的工作而非审批 Tab
- 终验零回边时，驳回后任务 cancelled 并显示 `approval_rejected`；一条回边时驳回进入重做；多条回边无法发布
- 或签提示：「任一人处理即生效，其余待办自动关闭」
- 提交后停留详情页并刷新，Tab 角标减一

### 3.7 产物

- 详情页与提交弹窗共用产物列表组件
- 内联预览：图片、纯文本、Markdown、PDF 首页；其他类型仅下载
- 下载走 24h 签名 URL，过期自动重签一次后提示重试
- 他人任务产物需 `artifact_read_all`，否则不显示下载入口

### 3.8 实时与刷新

- 订阅 `task.updated` / `artifact.updated`；当前详情页收到事件后局部刷新
- 断线时降级为 30s 轮询，恢复后停止
- 列表页只更新对应行，不整表重排

### 3.9 状态与异常

- 加载：骨架屏 3 行
- 空态：按 Tab 给不同文案（无可认领 / 无进行中 / 无待审批）
- 403：整页无权限提示，不显示任务内容
- 404：任务不存在（任务不提供物理删除）
- 服务不可用：顶部黄条 + 重试按钮

### 3.10 接口

| 用途 | 接口 |
|---|---|
| 列表 | `GET /api/tasks?state=&owner_id=&workflow_id=&limit=&offset=` |
| 创建并启动 | `POST /api/tasks` |
| 角标 | `GET /api/tasks/summary` |
| 详情 | `GET /api/tasks/{task_id}` |
| 认领 | `POST /api/tasks/{task_id}/nodes/{node_id}/claim` |
| 提交结果 | `POST /api/tasks/{task_id}/nodes/{node_id}/result` |
| 取消 | `POST /api/tasks/{task_id}/cancel` |
| 重跑汇聚 | `POST /api/tasks/{task_id}/nodes/{node_id}/rerun-join` |
| 审批列表 | `GET /api/approvals?state=pending` |
| 审批处理 | `POST /api/approvals/{approval_id}/resolve` |
| 产物下载 | `GET /api/artifacts/{artifact_id}/download` |

### 3.11 权限

- 页面/按钮条件见 2.4、2.5
- 数据范围由服务端按 `data_scope` 过滤
- 认领仅限岗位候选人；提交仅限当前 run 执行人

---

## 4. 工作流列表与版本页（已确认）

### 4.1 列表（卡片）

`/console/workflows`，响应式网格，每行 2–3 张卡片。

卡片内容：

- 名称、描述首行
- 状态：草稿 / 已发布 / 有草稿待发布
- `最新 vN`、`已发布 vM`
- 节点数、最近更新时间
- 悬浮操作：打开、新建版本、删除（有权限时）

顶部：搜索框 + 「新建工作流」。空态引导「从模板创建第一个工作流」。

### 4.2 新建：从模板开始

点击新建 → 模板选择弹窗（4 个）：

| 模板 | 结构 |
|---|---|
| 空白 | 仅 start |
| 串行执行 | start → agent → agent |
| 条件分支 | start → agent → condition → 两个 agent |
| 扇出汇总 | start → agent(fanout) → join → agent |

流程：选模板 → 填写名称 → 创建 v1 草稿 → 直接进入编辑器。

- 模板节点不带岗位，进编辑器后需绑定；发布校验会提示 `E_NODE_POSITION_REQUIRED`
- 模板是前端常量，通过 graph API 写入，不新增后端模板表

### 4.3 版本页

`/console/workflows/:id`，顶部工作流信息 + 版本表格。

列：版本 / 状态 / 节点数 / 创建时间 / 发布时间 / 操作。

行内操作：

- **打开编辑器**：草稿可编辑；已发布版本为只读（编辑时按交互稿派生草稿）
- **只读查看**：直接进编辑器只读态
- **发布**：仅草稿显示，需 `workflow_publish`
- **对比**：默认与上一版对比，可在弹窗切换基线
- **克隆**：以该版本为基准新建草稿

页面不再单独做版本详情页；所有查看/编辑都进编辑器。

### 4.4 发布与校验

- 点发布先调 `POST /api/workflows/{id}/versions/{v}/validate`
- 失败：弹窗列出错误（错误码、节点、说明），点击条目跳编辑器并选中定位；结构性错误（缺 start、空图）也走同一弹窗
- 通过：二次确认，提示「运行中任务仍锁定旧版本」，确认后发布
- 并发冲突：409 时提示版本已变化并刷新
- 发布成功：卡片与版本表状态更新，Toast 带版本号

### 4.5 软删除与派生

- 工作流删除为**软删除**，保留定义/版本标记及历史任务快照；有活跃 run 时返回 409，提示「存在运行中任务」，不自动取消
- 删除成功后不可再创建新任务，默认列表隐藏；历史任务详情按已保存的 run/结果展示，不依赖当前定义
- 已发布版本不能被单独物理删除；只能软删除整个工作流或克隆新版本
- 派生草稿规则见 [workflow-editor-ux.md](./workflow-editor-ux.md) 10.5

### 4.6 接口

| 用途 | 接口 |
|---|---|
| 列表 | `GET /api/workflows` |
| 详情 | `GET /api/workflows/{id}` |
| 版本列表 | `GET /api/workflows/{id}/versions` |
| 创建 | `POST /api/workflows`（含模板 graph） |
| 派生草稿 | `POST /api/workflows/{id}/versions/{v}/clone` |
| 校验 | `POST /api/workflows/{id}/versions/{v}/validate` |
| 发布 | `POST /api/workflows/{id}/versions/{v}/publish` |
| 删除 | `DELETE /api/workflows/{id}` |

### 4.7 权限

- 查看：登录即可
- 新建：`workflow_create`
- 打开编辑器/保存/克隆：`workflow_modify`
- 发布：`workflow_publish`
- 删除：`workflow_modify`

---

## 5. 组织页（已确认）

### 5.1 结构

`/console/organization?tab=staff|positions|roles|teams`

- **员工**：内分「真人 / Agent」两个子 Tab
- **岗位**：左右双栏
- **角色**：业务角色列表 + 详情
- **团队**：团队列表 + 工位网格

### 5.2 员工 · 真人

表格列：姓名 / 岗位 / 角色数 / 技能数 / 权限模板 / 工位 / 状态 / 最后活跃。

- 顶部：「邀请真人」按钮（`employee_invite`）
- 邀请弹窗：姓名、登录名、岗位、权限模板（默认员工）、`data_scope`（默认 self）→ 生成一次性邀请链接，复制给本人
- 链接默认 24h 有效、一次性、可撤销；过期或已使用访问返回 410。重发会作废旧链接并生成新链接，不延长旧链接
- 可授予权限与 data_scope 受邀请人自身上界限制；注册时服务端按邀请快照和当前上界再次校验
- 行点击打开右侧员工抽屉
- 移除员工：`employee_remove`，二次确认；存在进行中 run 时 409。成功为软移除，撤销会话并退出候选池，历史身份保留

### 5.3 员工 · Agent

表格列：Agent 名 / 外壳（framework · model）/ 岗位 / 技能 / 状态（在线/离线，注册记录不会被自动删除）/ 待办数 / 最后心跳。

- 行点击打开同一员工抽屉，档案页展示外壳信息与 token 状态（不显示明文）
- 「查看外壳」跳 `/console/agents?tab=shells&id=...`
- 注销：`agent_deregister`，二次确认；有活跃 run 返回 409。成功为软注销，撤销当前/旧 token 并退出候选池，历史 run 保留
- 邀请码生成不在本页，统一在系统组

### 5.4 员工抽屉（640px）

头部：头像（首字母）、姓名、类型标签、在线状态、岗位。

四个 Tab：

1. **档案**：姓名、登录名/外壳、联系方式、岗位、工位、入职时间；Agent 额外显示 framework/model/endpoint/channel_type/last_seen_at
2. **角色与技能**：业务角色绑定（`employee_role_bindings`）+ 技能标签（`employee_capabilities`）；增删需 `role_bind`
3. **权限**：模板下拉（超管/主管/员工/只读）+ 21 项权限勾选 + `data_scope`；仅 `console_admin` 可改，且授权上界仍由后端复核
4. **工位与联系人**：团队、工位选择，联系人增删（`employee_contacts`）

### 5.5 岗位（左右双栏）

左栏：岗位列表，显示名称、角色数、候选人数；顶部「新建岗位」（`org_manage`）。

右栏：

- 基本信息：名称、说明、是否启用
- 绑定角色：多选业务角色（`role_bind`），决定该岗位能承接哪些工作流节点
- 候选员工：当前绑定员工列表，可增删（`org_manage`）
- 关联信息：使用该岗位的节点数、进行中 run 数（只读）

### 5.6 角色

列表列：角色名 / 技能数 / 绑定岗位数 / 员工数 / 更新时间。

详情抽屉：

- 基本信息：名称、说明
- 技能（`capabilities`）：标签增删，用于调度时能力交集判断
- 绑定岗位：多选；被节点使用时不可删除（409）
- 绑定员工：多选

注意：这里是**业务角色**，不含登录权限；登录权限只属于员工（第 2 节）。

### 5.7 团队与工位

上半：团队列表（名称、主管、成员数、在线数）；可切换/新建团队。

下半：当前团队工位网格。

- 工位按 `seat_id` 排列，沿用大屏布局坐标
- 拖员工卡片到空工位即入座；拖回未分配区即取消
- 工位被占用返回 409，提示「该工位已被占用」
- 主管设置需 `org_manage`
- 工位变化即时反映到大屏

### 5.8 校验与异常

- Agent 员工必须绑定岗位，否则保存 422
- 移除员工有进行中 run → 409
- 删除角色仍被岗位/员工引用 → 409
- 真人邀请链接已撤销、过期或已使用 → 410；重发后旧链接同样返回 410
- 列表空态分别给「暂无真人 / 暂无 Agent / 暂无岗位 / 暂无角色 / 暂无团队」

### 5.9 接口

| 用途 | 接口 |
|---|---|
| 员工列表 | `GET /api/employees?type=human\|agent` |
| 邀请真人 | `POST /api/employees/invite` |
| 员工详情 | `GET /api/employees/{id}` |
| 更新员工 | `PATCH /api/employees/{id}` |
| 移除员工 | `DELETE /api/employees/{id}` |
| 权限读写 | `GET/PUT /api/employees/{id}/permissions` |
| 角色绑定 | `GET/PUT /api/employees/{id}/roles` |
| 技能读写 | `GET/PUT /api/employees/{id}/capabilities` |
| 岗位列表/详情 | `GET /api/positions`、`GET /api/positions/{id}` |
| 岗位角色 | `PUT /api/positions/{id}/roles` |
| 岗位员工 | `PUT /api/positions/{id}/employees` |
| 角色 CRUD | `GET/POST/PATCH/DELETE /api/roles` |
| 角色绑定 | `PUT /api/roles/{id}/positions`、`PUT /api/roles/{id}/employees` |
| 团队 | `GET/POST/PATCH /api/teams` |
| 脱敏员工选项 | `GET /api/options/employees?position_id=&limit=&offset=`（登录可读，供编辑器/任务表单） |
| 脱敏岗位选项 | `GET /api/options/positions?limit=&offset=`（登录可读，不返回组织管理字段） |
| 工位 | `GET /api/teams/{id}/seats`、`PUT /api/seats/{id}/assign` |

以上为前端冻结契约，后端按 Phase 2/4 补齐；本轮仅明确 `DELETE /api/employees/{id}` 表示软删除/停用，不据此推断角色等其他资源的删除语义。组织管理只使用 `/api/employees`、`/api/positions`、`/api/teams`，不保留旧路径运行时回退。

### 5.10 权限

- 员工 Tab 可见：`org_manage` 或 `employee_invite`
- 岗位/团队：`org_manage`
- 角色：`role_manage`
- 绑定角色/技能：`role_bind`
- 权限 Tab：`console_admin`
- 邀请/移除：`employee_invite` / `employee_remove`

---

## 6. 协同大屏、消息、指标、审计（已确认）

### 6.1 协同大屏与孪生展示

本节同时约束展示端 `/twin` 与管理端 `/console/collab`，两端共用 `collab_screens` 一张屏幕表，不再区分“管理端屏幕”和“大屏会话”。

#### 6.1.1 屏幕模型与生命周期

- `/twin` 首次打开自动匿名登记屏幕（`POST /api/public/collab/screens`），生成 `screen_id` 与一次性 `screen_secret`；服务端只存 `secret` 的不可逆哈希，明文仅在该登记响应返回一次。设备把它写入 `localStorage`（键 `mailbus.screen`），跨标签、刷新、关浏览器与设备重启均复用；心跳与离线上报携带 `X-Screen-Secret`。无持久化能力时（隐私模式等）每次按新屏登记，不保证接管配置保留。屏幕心跳只更新屏幕在线状态，不保活任何员工会话。
- `/console/collab` 接管自动登记的屏幕：重命名、绑定团队、配置布局/主题/分辨率、发布、定向投送、清理。管理端不提供“手工新建屏幕”，避免与自动登记产生两套 ID。
- 管理端「全屏打开」使用 `/twin?screen_id=...&preview=1`：只读该屏已发布配置，不登记、不发心跳、不接收聚焦，不作为投送目标；物理大屏仍由设备上的 `/twin` 自动登记。目标屏不存在返回 404 空态，屏幕离线或无已发布配置时显示「该屏幕未配置」空态。
- `/twin?screen_id=` 仅在设备持有对应 `screen_id` 与 `secret` 时复用该屏；设备本地无记录、或被管理端重置后，一律按**新屏**登记并生成新 ID，绝不覆盖已有屏幕配置；不带 `screen_id` 同样视为新屏。
- 心跳 30 秒；超过 60 秒无心跳判离线，列表置灰并显示最后心跳。仅离线屏幕可删除；60 秒内有心跳的屏幕删除返回 409「屏幕正在播放」。
- 仅清理**从未被管理端接管**（未改名、未绑定团队、未发布配置）且离线超过 30 天的自动登记屏幕；已配置屏幕不自动删除。公开登记按 IP 限速 10 次/分钟，超限 429；在线自动屏上限 64 台，超出返回 503，防止无限造屏。
- 已绑定团队、布局或主题的屏幕被重新打开时，继续使用服务端已发布配置，不因新标签丢失。

#### 6.1.2 展示端 `/twin`（匿名 kiosk）

- 默认匿名只读 kiosk，无需登录；kiosk 不显示登录入口、侧栏、员工名册、工位详情抽屉和页脚 API 信息。
- kiosk 保留楼层切换、缩放/复位、状态图例、聚焦提示和断线重连提示；工位不可点开详情。
- 登录员工可在顶栏切换交互模式：恢复侧栏、名册、工位详情与任务创建入口，按当前员工 `permissions` 取数；数据范围取「屏幕绑定团队」与「本人 `data_scope`」的交集，屏幕未绑定团队时按本人 `data_scope`；创建任务遵循 `task_create`，代派需 `task_create + task_dispatch`，不提供草稿或直接改状态。登录复用控制台登录页并回跳 `/twin`，不在大屏内嵌独立账号体系。
- 交互模式连续 5 分钟无操作自动退出并回到匿名 kiosk；手动退出登录立即回到 kiosk。匿名模式不可发起任务，`?preview=1` 始终只读且不提供登录切换。
- 默认使用屏幕已发布配置；未配置时按办公室布局、自动主题、1920×1080 渲染。
- 公开投影字段白名单：姓名、岗位、Agent 名、任务标题、任务状态、当前节点、节点状态、进度、`seat_id`、结对关系、消息气泡。不返回 `employee_id / agent_id / team_id / endpoint / token / created_by` 等内部标识，也不返回团队名称 `team`；团队仅用于服务端过滤。绑定团队后仅渲染该团队成员，其他工位留空。
- 任务状态统一 `pending / running / blocked / done / cancelled / failed`；工位视觉状态 `idle / running / waiting_human / failed / done`。同一工位存在多个活跃节点时显示「并发 N」角标，扇出分片计入 N。
- 结对线：`collab_pairs.state=active` 的两人之间画一条线，结束后淡出；同一对不叠加多条线。本期不新增控制台结对管理页，创建/结束沿用现有 `POST /api/collab/pairs` 与 `/end`，由员工或 Agent 侧调用，控制台与大屏均不提供结对管理入口，大屏只展示。
- 气泡：同层结对消息与 `task_assignment` 摘要按时间合并；`task_assignment` 摘要取任务标题，同任务存在多个节点时追加当前节点名；每条结对只显示最新 1 条，前端最多缓冲 3 条；正文超过 40 字截断；不展示附件、payload 与内部 ID。
- 实时：公开 SSE 只消费 `pair.started / pair.ended / message.created / task.updated / screen.config / screen.focus`；`screen.registered` 不进公开流，管理端列表自行刷新获取；断线按 1s→30s 指数退避重连，重连后重新拉取布局与消息快照；连接上限返回 503 时同样退避，不显示错误页。
- 公开配置接口不返回 `team_id`，只返回 `team_bound` 与布局/主题/分辨率；团队过滤在服务端完成。
- 主题：屏幕配置 `dark/light` 优先；`auto` 时按浏览器本地时间 19:00–06:00 切夜间，跨边界自动切换，无需刷新。
- `prefers-reduced-motion` 时关闭走动人、脉冲和气泡动画，仅保留状态变化。

#### 6.1.3 布局

- 三种布局：`office` 使用现有办公室布局；`grid` 按绑定团队自动生成等距网格；`custom` 在控制台可视化编辑。
- `grid` 必须绑定团队；管理员只选行/列上限与排序字段（姓名 / 岗位 / 工位），不单独存工位数据；未绑定团队时保存 422，大屏显示「请先绑定团队」空态。
- `custom` 使用可视化编辑器：拖拽房间与工位、修改坐标和名称、增删楼层，保存为布局 JSON；复用 `ScreenPreview` 的 SVG 舞台，不新增拖拽依赖。
- 布局 JSON 存于屏幕 `config_json`，字段为 `layout_type / theme / resolution / team_id / play_state / office / grid / custom`。
- 分辨率固定 1920×1080、3840×2160 两档，只影响预览画布比例，不改变布局坐标。

#### 6.1.4 管理端 `/console/collab`

`/console/collab`，左右布局：

- 左栏 280：屏幕列表（名称、绑定团队、布局、分辨率、在线状态、最后心跳、来源 `auto/manual`）；顶部只有「刷新」，不提供手工新建。
- 右栏：配置页签 + 预览。
  - 布局：三选一；`grid` 显示行/列/排序；`custom` 进入编辑器；`office` 只读展示现有楼层。
  - 主题：`auto / dark / light`。
  - 分辨率：1920×1080 / 3840×2160。
  - 绑定团队：单选，可清空；`grid` 必填。
  - 播放状态：`playing / paused`；暂停仅停止应用新发布配置，任务、消息、结对等实时数据继续更新，草稿与 `config_version` 不受影响。
- 保存只写草稿 `config_json`；点「发布」快照为 `published_config_json` 并使 `config_version+1`，通过 SSE `screen.config` 推送，30 秒内生效；屏幕离线时在下次心跳或重连拉取。
- 预览：16:9 只读，与 `/twin` 同源组件，使用草稿配置。
- 远程聚焦：选中屏幕后，在预览或楼层图选中楼层/工位，点「投送到此屏」；一次性指令，不改配置、不持久化；目标屏离线返回 409；同浏览器其他标签继续本地同步，其他屏幕不跟随。
- 删除：仅离线屏幕可删，二次确认；删除移除屏幕记录，不影响布局、消息与历史。

#### 6.1.5 权限与异常

- `/console/collab`：`console_admin`；`/twin` 匿名 kiosk 只读，交互模式需登录，任务创建额外要求 `task_create`。
- 在线屏幕删除 409；`grid` 未绑定团队保存 422；发布空布局 422；聚焦目标离线 409；公开登记超限 429；在线自动屏超 64 台 503；公开 SSE 满 503；交互模式无权限发起任务 403；`preview=1` 目标屏不存在 404。

### 6.2 消息与追迹

`/console/messages`，双 Tab。

**消息流**

- 筛选：员工、通道（web / a2a / file_bus）、类型（message / command / task_assignment / task_cancel）、方向、时间；服务端按本人/本团队成员是发送方或接收方应用数据范围
- 列：时间、发送方 → 接收方、类型、通道、摘要、关联任务
- 点击行打开右侧详情抽屉：完整正文、payload、附件、投递尝试记录、关联任务跳转
- 右上「发消息」（`message_send`）：选接收员工、类型、正文；发送后插入列表顶部
- 实时订阅 `message.created`，新消息高亮 2 秒

**任务追迹**

- 顶部搜索 task_id 或从任务详情跳入
- 时间线合并该任务的消息、节点事件、产物、审批，按时间排序
- 支持按事件类型过滤；只读

### 6.3 指标与报表

`/console/metrics`，固定看板 + 时间筛选（7 天 / 30 天 / 自定义）。

- 指标卡：任务总量、进行中、完成率、平均完成时长、失败率、升级数、在线 Agent、待办积压
- 趋势图：任务创建/完成、平均节点时长
- 排行表：工作流完成率与平均时长、Agent 负载与失败率
- 导出：当前筛选结果 CSV；与指标接口复用同一服务端 `data_scope` 过滤结果，不另做全量聚合后裁剪
- 空态与加载骨架；指标口径在页面问号提示中说明

### 6.4 审计与告警

`/console/audit`，双 Tab。

**审计日志**

- 筛选：操作人、动作、资源类型/ID、时间、结果
- 列：时间、操作人、动作、资源、结果、IP
- 详情抽屉：请求摘要、变更前后 JSON diff（字段级高亮）
- 导出 CSV；保留期沿用服务端策略

**告警**

- 状态：触发中 / 已确认 / 已恢复
- 列表列：类型、级别、对象、触发时间、持续时长、状态
- 详情：触发条件、当前值、关联对象跳转
- 操作：确认、恢复（需 `log_read` + `console_admin` 之一）

**通知规则**（子页签）

- 规则列表：名称、告警类型、阈值、渠道、接收人、启用
- 新建/编辑抽屉：类型、阈值、渠道（webhook / 邮件 / 站内）、接收人、通知冷却秒数 `silence_seconds`、启用
- 冷却含义提示为「同一规则、同一资源两次通知的最小间隔」，不是每日静默时段
- 仅进入 firing 时通知；恢复自动置 resolved 但不发恢复通知。webhook/邮件超时 5 秒、指数退避重试 3 次，最终失败写审计并在详情可见
- 「测试发送」按钮；删除二次确认
- 预置告警类型：Agent 离线 >5 分钟、run 超时、升级待处理 >1 小时、outbox 积压 >100、工作流失败率 >20%（1 小时）

权限：审计 Tab `log_read`；告警与通知规则 `console_admin`。

### 6.5 接口

| 用途 | 接口 |
|---|---|
| 屏幕列表/详情/更新/删除 | `GET /api/collab/screens`、`GET/PATCH/DELETE /api/collab/screens/{id}` |
| 发布布局 | `POST /api/collab/screens/{id}/publish` |
| 远程聚焦 | `POST /api/collab/screens/{id}/focus` |
| 结对列表/创建/结束 | `GET/POST /api/collab/pairs`、`POST /api/collab/pairs/{id}/end` |
| 公开登记/心跳/离开 | `POST /api/public/collab/screens`、`POST /api/public/collab/screens/{id}/heartbeat`、`POST /api/public/collab/screens/{id}/leave` |
| 公开屏幕配置 | `GET /api/public/collab/screens/{id}/config` |
| 公开布局/消息/任务/工位 | `GET /api/public/layout?screen_id=`、`GET /api/public/collab/messages?pair_id=&limit=`、`GET /api/public/collab/tasks/{task_id}`、`GET /api/public/collab/seats/{seat_id}/tasks` |
| 公开实时流 | `GET /api/public/collab/stream?screen_id=` |
| 消息列表 | `GET /api/messages?employee_id=&channel=&kind=&limit=&offset=` |
| 消息详情 | `GET /api/messages/{id}` |
| 发消息 | `POST /api/messages` |
| 任务追迹 | `GET /api/tasks/{id}/trace` |
| 指标总览 | `GET /api/metrics/overview?from=&to=` |
| 指标趋势 | `GET /api/metrics/trend?from=&to=&bucket=day` |
| 指标排行 | `GET /api/metrics/breakdown?from=&to=` |
| 指标导出 | `GET /api/metrics/export?from=&to=` |
| 审计列表/详情 | `GET /api/audit?actor=&action=&resource=&from=&to=`、`GET /api/audit/{id}` |
| 告警列表/确认 | `GET /api/alerts?state=`、`POST /api/alerts/{id}/ack` |
| 通知规则 | `GET/POST/PATCH/DELETE /api/alert-rules`、`POST /api/alert-rules/{id}/test` |

公开配置接口不返回 `team_id`，只返回 `team_bound`；`?preview=1` 只读已发布配置，不登记、不发心跳、不接收聚焦。

### 6.6 后端新增（需回写设计）

- `ops_alerts`、`ops_alert_rules` 两张表（迁移 033）
- `collab_screens` 增加草稿/已发布配置：`config_json`、`published_config_json`、`config_version`、`source`、`updated_at`；`team_id/layout_type/theme/resolution/play_state` 存放在配置 JSON 内（迁移 035）
- 公开屏幕配置接口只返回已发布配置；`/twin` 不读取草稿
- 公开登记限速与离线清理；心跳 30 秒、离线阈值 60 秒
- 公开 SSE 事件白名单补充 `screen.config`、`screen.focus`，且只向目标 `screen_id` 发送聚焦
- 工位状态映射到 `pending/running/blocked/done/cancelled/failed` 与 `idle/running/waiting_human/failed/done`；同工位多活跃节点返回并发数
- 气泡聚合：按 `pair_id` 取最新结对消息，并合并 `task_assignment` 摘要
- 通知适配器：webhook / 邮件 / 站内；APScheduler 周期检测
- 指标聚合接口与 CSV 导出
- 任务追迹聚合接口
- 消息列表按新 `kind` 过滤、实时事件 `message.created`

---

## 7. Agent 与接入、集成、设置向导（已确认）

### 7.1 Agent 与接入

`/console/agents?tab=shells|invites`。

**外壳 Tab（卡片）**

- 响应式卡片，每行 2–3 张
- 卡片内容：Agent 名、`framework · model`、通道/类型标签、在线圆点、待办数、最后心跳、所属员工与岗位
- 卡片操作：查看详情、轮转 token、解绑员工、注销
- 点击卡片打开 560px 抽屉：
  - 基本信息：agent_id、类型、通道、endpoint、health_url、创建时间；展示 endpoint 审批状态（待审批/已批准/已拒绝）及待审批地址
  - endpoint 审批：仅 `console_admin` 可见；查看旧/新地址与校验结果后批准或拒绝。待审批期间明确显示「暂停新任务投递」，不能仅显示在线就认为可派单
  - 鉴权：token 指纹、上次轮转时间、「轮转 token」（新 token 仅展示一次，旧 token 24h 内仍有效；服务端当前/旧 token 均加密落库，界面与日志永不显示明文）
  - 连接：健康检查按钮，显示最近一次结果与延迟
  - 最近任务：最近 5 条 run，跳任务详情

**邀请码 Tab**

- 表格列：码前缀、员工名、岗位、创建人、创建时间、有效期、状态、使用人
- 状态：未使用 / 已使用 / 已撤销 / 已过期（未设有效期显示「长期有效」）
- 操作：查看详情、作废（二次确认）；明文只在生成结果中复制，列表不能再次读取或复制完整邀请码
- 顶部「生成邀请码」

生成弹窗：员工名、岗位、业务角色/技能、权限模板、`data_scope`（默认 self）、`agent_type`、`channel_type`、有效期（1h / 24h / 7d / 长期，默认长期）。权限和 data_scope 选项按当前用户授权上界过滤，后端仍需复核。

生成结果弹窗：邀请码 + 三个可复制页签：

1. **HTTP 注册**：curl 示例（`POST /api/agents/register`）
2. **MCP 配置**：Trae/Cursor 的 4 工具配置片段
3. **system_prompt / Skill**：豆包、元宝、hermes 的接入说明

提示「邀请码明文只展示一次，用后即废，请立即保存或发送」。

### 7.2 集成

`/console/integrations`，保留现有四块并改版：

- 集成列表：名称、类型、描述、可用动作、配置状态
- 调用调试：选集成与动作、填参数、展示响应；仅调试，不落业务数据
- 插件：启用/移除
- 运行配置：按组展示环境变量，敏感值脱敏，修改需二次确认；支持重载

### 7.3 设置向导

保留现有 3 步：超管创建 → 模型配置 → 首个团队；均支持跳过。

完成后展示「接下来」卡片：

- 接入首个 Agent → `/console/agents?tab=invites`
- 创建首个工作流 → `/console/workflows`
- 打开大屏 → `/twin`

已完成步骤显示完成时间；重复进入不再强制引导。

### 7.4 接口

| 用途 | 接口 |
|---|---|
| 外壳列表/详情 | `GET /api/agents`、`GET /api/agents/{id}` |
| 轮转 token | `POST /api/agents/{id}/rotate-token` |
| 健康检查 | `POST /api/agents/{id}/health` |
| endpoint 审批 | `POST /api/agents/{id}/endpoint/approve`、`POST /api/agents/{id}/endpoint/reject` |
| 解绑员工 | `POST /api/agents/{id}/unbind` |
| 注销 | `DELETE /api/agents/{id}` |
| 生成邀请码 | `POST /api/agent-invites` |
| 邀请码列表 | `GET /api/agent-invites` |
| 作废邀请码 | `POST /api/agent-invites/{id}/revoke` |
| 集成 | 现有 `/api/settings/integrations`、`/api/settings/env`、`/api/dev/reload` |
| 向导 | 现有 `/api/identity/bootstrap` 系列 |

### 7.5 权限

- 外壳 Tab：`org_manage` 或 `agent_deregister`；endpoint 审批仅 `console_admin`
- 邀请码 Tab：`console_admin`
- 集成/设置向导：`system_config`
- 轮转/解绑/注销：`console_admin`（注销也可 `agent_deregister`）

### 7.6 后端调整

- `agent_registration_invites.expires_at` 允许为空（长期有效），增加 `revoked_at` / `revoked_by`
- 邀请码校验顺序：不存在 404 → 已使用 409 → 已撤销/已过期 410
- Agent 列表补充 `pending_task_count`、`last_seen_at`、员工与岗位字段
- 轮转 token 需返回新 token 一次，旧 token 保留 24h；当前/旧 token 使用 `MAILBUS_TOKEN_ENCRYPTION_KEY` 加密落库，另存不可逆 lookup digest 用于入站反查，界面只显示指纹
- 首次注册及 heartbeat 改 endpoint 均进入待审批并暂停新任务投递；审批/拒绝接口仅超管可用，注册、审批与投递前执行 SSRF 与可信网段校验
- 现有 6 个 Agent 切换前逐一补岗位、审批 endpoint、签发新 token 并回归；全部就绪后一次切换并删除旧 transport，不长期保留双引擎

---

## 8. 最终跨端契约（冻结）

1. **列表**：所有分页列表返回 `{items,total,limit,offset}`；前端领域 API 统一解包，不接受裸数组。
2. **时间**：JSON 请求/响应统一 ISO 8601 UTC；`format.ts` 负责本地展示。数据库 REAL epoch 秒只存在于服务端适配层，不泄漏为 JSON 时间格式。
3. **组织路径**：只使用 `/api/employees`、`/api/positions`、`/api/teams`；不实现 `/api/identity/staff`、`/api/org/positions`、`/api/org/teams` 运行时回退。
4. **选项接口**：编辑器与任务表单只读 `/api/options/employees`、`/api/options/positions` 的脱敏选项，不用完整组织管理接口充当公开下拉。
5. **Graph 保存**：使用 `{graph,revision}` 整数乐观锁；409 后重新加载或 `force=true` 覆盖，覆盖仍递增 revision 并写审计。
6. **错误**：沿用 `{error,error_code,message_zh}`；400/401/403/404/409/410/413/422 按场景处理，不能仅显示通用失败。
7. **生命周期**：员工、Agent、工作流软删除/停用，有活跃 run 返回 409；任务只有取消，没有物理删除。
8. **外部产物**：外部 Agent 必须先 PUT 签名 URL 并引用返回的 `artifact_id`，或走受限 base64 内联；前端不提交 `type=url`，mailbus 不抓取任意外部 URL。
9. **大屏访问**：`/twin` 默认匿名只读；登录员工可切交互模式，按本人权限与数据范围取数并发起任务；公开投影只返回姓名、岗位、Agent 名、任务、节点、进度、`seat_id` 与结对/气泡，不返回 `employee_id / agent_id / team_id / endpoint / token / created_by`。
10. **屏幕模型**：`/twin` 自动登记与 `/console/collab` 共用 `collab_screens`；配置分草稿 `config_json` 与已发布 `published_config_json`，发布使 `config_version+1`；30 秒心跳、60 秒判离线，仅离线可删除。
11. **布局**：`office / grid / custom` 三模式；`grid` 必须绑定团队；`custom` 使用控制台可视化编辑器；分辨率仅 1920×1080 / 3840×2160 两档。
12. **同步范围**：以上契约由 Python、Java、前端与 mock 同步实现；本文冻结不代表业务代码已经完成。






