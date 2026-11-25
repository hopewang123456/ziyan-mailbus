# 前端实施计划

> 2026-11-25 · v1.2 依据最终冻结需求编制，不代表已开工
> 需求来源：[frontend-requirements.md](./frontend-requirements.md)、[workflow-editor-ux.md](./workflow-editor-ux.md)、[agent-unification-design.md](./agent-unification-design.md)

---

## 0. 实施目标与约束

### 目标

- 将现有平铺控制台一次性替换为 5 组、13 个页面的新版控制台
- 完成任务中心、组织、工作流编辑器、Agent 接入等新增闭环
- 后端未完成时使用可重复的开发 mock；发布前全部切换真实接口
- 普通员工、主管、只读、超管看到与权限矩阵一致的导航和操作

### 约束

- 保持 React 19 + Vite 6 + TypeScript + Tailwind 3 + React Router 7
- 不引入 Redux、Zustand、React Query 或大型 UI 组件库
- 运行时新增依赖仅：
  - `@xyflow/react`
  - `@uiw/react-codemirror`、`@codemirror/lang-json`
- 图表继续使用轻量 SVG，不新增图表库；3D 预览复用 `src/twin/`
- 桌面优先：1280 为主要验收宽度，1024 为最小验收宽度；不做移动端
- 新旧控制台不并存、不做灰度开关；内部分阶段实现，最终一次替换

---

## 1. 现状与必须优先消除的差距

| 现状 | 目标 | 实施动作 |
|---|---|---|
| `useConsoleAccess` 只允许 `*` / `console_admin` 进入 | 所有有效登录员工均可进入，页面按权限过滤 | 第一阶段先改门禁，否则普通员工流程无法验收 |
| 权限字段为 `capabilities`，`can()` 散落页面 | 契约改为 `permissions`，21 个权限点集中判断 | 建立 `lib/permissions.ts`，页面只消费 `can()` |
| 12 个平铺导航，路由与导航分别判断 | 5 组导航，导航与路由共用同一可见性配置 | 建立 `lib/navigation.ts` |
| 未授权路由多数回落概览 | 隐藏导航，但直达已存在路由显示 403 | 增加 `RequirePermission` 与统一 403 页 |
| 页面直接写 API 路径 | 每个领域集中维护 DTO 与路径 | 建立 `lib/<domain>/api.ts` |
| `api()` 对任意 body 默认 JSON Content-Type | 产物上传需要 FormData | 仅字符串 JSON 自动加头，FormData 交给浏览器 |
| SSE 工具位于 `twin/stream.ts` | 控制台任务、消息也要复用 | 抽取通用 `lib/events.ts`，保留 twin 兼容入口 |
| 测试以 SSR 字符串断言为主 | 交互、冲突、表单需要 DOM 测试 | 保留 SSR  smoke，补 jsdom + Testing Library |
| `ConsoleTable` 与旧 `DataTable` 并存 | 统一 ConsoleKit | 全量迁移后删除无引用旧组件 |

### 冻结契约基线

当前代码使用 `/api/identity/staff`、`/api/org/positions`、`/api/org/teams`，最终契约已统一为 `/api/employees`、`/api/positions`、`/api/teams`。F0 按以下基线建立共享 DTO 与领域 API，不再保留待选路径：

- 页面不得同时实现两套路径或运行时自动回退
- mock 与真实请求都通过同一个领域 `api.ts`
- 所有分页列表统一解包 `{items,total,limit,offset}`，不接受裸数组
- JSON 时间统一 ISO 8601 UTC，由 `format.ts` 转本地展示；DB REAL epoch 秒不进入前端 DTO
- 错误结构沿用 `{error,error_code,message_zh}`；统一使用后端 snake_case DTO，展示格式在前端转换
- Graph 保存统一 `{graph,revision}`，`force=true` 覆盖仍递增 revision 并写审计；不使用 `expected_updated_at`
- 编辑器/任务表单使用 `/api/options/employees`、`/api/options/positions` 脱敏选项接口，不调用完整组织管理接口获取公开下拉

---

## 2. 目标代码结构

延续现有 `pages / components / lib` 分层，不另建复杂应用框架。路由页面保持薄壳，领域组件和请求分别集中。

```text
web/src/
  App.tsx                         公共路由、顶层旧地址重定向
  pages/console/
    ConsoleApp.tsx                门禁、布局、懒加载路由
    ConsoleOverviewPage.tsx
    ConsoleTasksPage.tsx          任务中心三 Tab
    TaskDetailPage.tsx
    ConsoleOrganizationPage.tsx   员工/岗位/角色/团队
    ConsoleWorkflowsPage.tsx      卡片列表
    WorkflowVersionsPage.tsx
    WorkflowEditorPage.tsx
    WorkflowDiffPage.tsx
    ConsoleAgentsPage.tsx         外壳/邀请码
    ConsoleMessagesPage.tsx
    ConsoleMetricsPage.tsx
    ConsoleCollabPage.tsx
    ConsoleAuditPage.tsx
    ConsoleSkillsPage.tsx
    ConsoleIntegrationsPage.tsx
    ConsoleSetupPage.tsx

  components/console/
    ConsoleLayout.tsx             分组侧栏、fluid 全宽模式
    ConsoleKit.tsx                表格、页头、区块、标签
    ConsoleTabs.tsx
    ConsoleDrawer.tsx
    ConsoleDialog.tsx             原生 dialog、焦点返回、Esc
    ConsolePageState.tsx          loading / empty / error / 403 / 404
    ConsoleToastHub.tsx           成功、提示、写操作失败
    RequirePermission.tsx

  components/tasks/
    TaskFilterBar.tsx
    TaskTable.tsx
    MyWorkBoard.tsx
    TaskTimeline.tsx
    CurrentRunCard.tsx
    ResultSubmitDialog.tsx
    ApprovalCard.tsx
    ArtifactList.tsx
    TaskEventList.tsx

  components/organization/
    EmployeeTable.tsx
    EmployeeDrawer.tsx
    PermissionEditor.tsx
    PositionMasterDetail.tsx
    RoleTable.tsx
    RoleDrawer.tsx
    TeamSeatBoard.tsx

  components/workflows/
    WorkflowCardGrid.tsx
    WorkflowTemplateDialog.tsx
    VersionTable.tsx
    PublishValidationDialog.tsx
    CloneDraftDialog.tsx

  components/workflow/editor/      按交互稿第 15 节原样落地
  components/agents/
  components/messages/
  components/metrics/
  components/audit/
  components/collab/

  lib/
    api.ts                        唯一网络入口
    console-access.ts             登录身份、permissions、data_scope
    permissions.ts                21 权限点、模板、can/canAny
    navigation.ts                 分组、页面、路由可见性同一数据源
    events.ts                     fetch SSE、重连、可见性恢复
    query.ts                      轻量请求 hook：取消、加载、错误、刷新
    format.ts                     时间、相对时间、数字、状态文案
    csv.ts                        统一 CSV 导出与 BOM
    tasks/api.ts + types.ts
    organization/api.ts + types.ts
    agents/api.ts + types.ts
    messages/api.ts + types.ts
    metrics/api.ts + types.ts
    audit/api.ts + types.ts
    collab/api.ts + types.ts
    workflow/                     graph/condition/promptVars/diff/layout/api

  mocks/
    index.ts                      仅开发环境动态加载
    router.ts                     按 method + path 分发
    fixtures/                     各领域确定性数据
    scenarios.ts                  ready/empty/denied/conflict/offline
```

### 状态管理约定

- 不建立全局业务 store；页面和领域组件使用局部 state/reducer
- Tab、筛选、选中版本等可分享状态写 URL search params
- 登录身份、权限、Toast 使用 Context；业务列表不复制到 Context
- `query.ts` 只解决请求取消、竞态、加载和错误，不做复杂缓存
- 编辑器使用独立 reducer + 历史栈，保存前不自动写后端

---

## 3. 路由、门禁与布局实施

### 3.1 路由清单

```text
/console
/console/metrics
/console/tasks?tab=all|mine|approvals
/console/tasks/:taskId
/console/messages?tab=stream|trace
/console/collab
/console/organization?tab=staff|positions|roles|teams
/console/workflows
/console/workflows/:workflowId
/console/workflows/:workflowId/versions/:version/editor
/console/workflows/:workflowId/versions/:version/diff/:other
/console/skills
/console/agents?tab=shells|invites
/console/integrations
/console/audit?tab=logs|alerts|rules
/console/setup
/twin
/join
```

### 3.2 门禁规则

- 无 token：保留 bootstrap 检查和 Token 登录入口
- 有效登录员工：进入控制台；普通员工不再因缺少 `console_admin` 被拒绝
- `can(permission)`：`permissions` 含 `*`、`console_admin` 或目标权限即通过
- 页面不可见：导航不渲染；直接访问已存在页面显示统一 403，不跳概览
- 未知路由：保留回概览
- 权限变更后重新拉取 `/api/identity/me`，导航与当前页面同步更新
- 列表数据由服务端按 `data_scope` 过滤，前端不做二次裁剪；self/team/global 按发起人或历史 run/审批参与者判定，消息按收发双方，指标和 CSV 复用同一过滤结果
- 无权限按钮不渲染；只读身份不显示提交类按钮，编辑器只读态禁用全部编辑入口
- 服务端仍是最终鉴权方，前端隐藏按钮不代替后端校验

### 3.3 重定向

```text
/console/staff     -> /console/organization?tab=staff
/console/teams     -> /console/organization?tab=teams
/console/approvals -> /console/tasks?tab=approvals
/staff             -> /console/organization?tab=staff
/teams             -> /console/organization?tab=teams
/approvals         -> /console/tasks?tab=approvals
```

其余现有顶层旧地址继续指向对应 `/console/*` 页面；避免多级重定向链。

### 3.4 布局

- `ConsoleLayout` 接收结构化分组导航，不再接收拼接好的 nav 节点
- 组内至少一个页面可见才显示组标题
- 默认内容区保留合适最大宽度；卡片、双栏和任务详情使用 `wide`
- 编辑器、diff 使用 `fluid`，去掉居中容器限制
- 编辑器与 diff 路由 `React.lazy`；3D 预览和 CodeMirror 二次按需加载

---

## 4. 公共机制先行

### 4.1 ConsoleKit 与基础组件

优先实现会被三个以上页面复用的组件：

- `ConsoleTabs`：与 URL 同步，支持角标
- `ConsoleDrawer`：560/640px，焦点圈定、Esc、关闭后焦点返回
- `ConsoleDialog`：确认、表单、错误清单共用
- `ConsolePageState`：骨架屏、空态、错误、403、404、服务不可用
- `ConsoleToastHub`：合并现有 `WriteFailToast`，保留全局写失败事件
- `ConfirmDialog`：危险操作统一确认，不单独拼浏览器 `confirm`

不抽一次性业务组件；简单输入框和按钮继续沿用现有 Tailwind / `hud-*` 样式。

### 4.2 请求与错误

- 保留 `ApiResult<T>`，业务层不抛未捕获异常
- GET 请求支持 AbortSignal，旧响应不得覆盖新筛选结果
- 领域 API 模块统一处理路径编码、query 和响应 DTO
- 写操作统一处理：
  - 400/422：字段或业务校验，保留用户输入
  - 401：回到登录门禁
  - 403：无权限提示
  - 404：资源不存在
  - 409：按场景处理冲突，不使用通用 Toast 了事
  - 410：真人邀请已撤销/过期/已使用；Agent 邀请码已撤销/过期（Agent 已使用为 409）
  - 0/5xx：服务不可用与重试
- FormData 上传不设置 JSON Content-Type；上传中禁用提交
- 下载统一处理签名 URL、过期重签一次和 blob 文件名

### 4.3 实时事件

从 `twin/stream.ts` 抽取并复用：

- 保留 fetch SSE，以支持 Authorization，不改用无请求头的原生 EventSource
- 保留分帧、心跳超时、指数退避、页面可见性恢复
- 事件类型：`task.updated`、`artifact.updated`、`message.created`
- 任务详情局部刷新；列表只更新受影响行
- 任务页断线降级 30s 轮询，SSE 恢复后停止
- 导航角标首次请求 `/api/tasks/summary`，之后由任务事件刷新，不轮询

---

## 5. 分阶段实施顺序

每个阶段完成真实浏览器验收后再进入下一阶段；mock 只解除前后端并行阻塞，不作为最终完成标准。

### F0：契约、门禁与基础设施

**工作项**

1. 按冻结基线建立控制台 API 路径、DTO、列表包装、UTC 时间、revision 与错误码处理
2. 增加运行时依赖；增加 `typecheck` 脚本和 DOM 测试环境
3. 改造 `console-access.ts`、`permissions.ts`、`navigation.ts`
4. 实现分组侧栏、wide/fluid、路由懒加载和重定向
5. 实现公共 Dialog/Drawer/Tabs/PageState/Toast
6. 抽取 SSE；扩展 API 上传、下载、取消和错误处理
7. 建立开发 mock 入口与测试工具

**阶段门禁**

- 普通员工可登录，只看到允许的页面；直达无权限页面为 403
- 超管、主管、员工、只读四种身份的导航快照与权限矩阵一致
- 1024/1280 下侧栏、内容区、Drawer/Dialog 可用
- `npm run typecheck`、现有测试、`npm run build` 通过

### F1：组织与 Agent 接入

**先做组织**

1. 员工真人/Agent 子 Tab、员工抽屉四页签
2. 真人邀请（默认员工模板、`data_scope=self`）、24h 一次性链接复制、撤销/重发、已使用/过期 410、员工软移除与活跃 run 409
3. 权限模板与 21 项权限编辑器；邀请和编辑均只展示当前用户可授权子集，后端上界错误保留表单并提示
4. 岗位左右双栏、角色列表/抽屉、绑定关系
5. 团队与工位网格、拖拽入座及 409 冲突

**再做 Agent 接入**

1. 外壳卡片与详情抽屉，展示已审批 endpoint、pending_endpoint 与审批状态
2. token 轮转（旧 token 24h 内有效）、健康检查、解绑、软注销；有活跃 run 返回 409
3. endpoint 批准/拒绝操作，仅超管可见；待审批期间显示暂停新任务投递，不把在线等同可派单
4. 邀请码生成（权限/data_scope 上界、1h / 24h / 7d / 长期，默认长期）、列表、作废
5. 邀请结果三页签：HTTP curl / MCP / system_prompt·Skill；完整邀请码仅在生成结果复制一次
6. 未使用 / 已使用 / 已撤销 / 已过期状态展示；未设有效期显示「长期有效」

**阶段门禁**

- 岗位无候选人、Agent 未绑岗位等 422 能保留输入并明确提示
- 员工有进行中 run、角色被引用、工位被占用的 409 均有独立反馈
- token 与邀请码明文只在成功响应后展示一次，不进入日志和持久化存储；token 在服务端仅以密文与不可逆 lookup digest 持久化，界面只显示指纹
- endpoint 变更后必须审批才恢复派单；拒绝/待审批状态和 SSRF 校验失败原因清晰可见
- 真人邀请重发后旧链接返回 410；Agent 邀请码已使用返回 409、撤销/过期返回 410

### F2：工作流列表、版本、编辑器与 diff

**F2a 列表与版本**

1. 工作流卡片网格、搜索、空态
2. 四模板选择、名称填写、创建 v1 并进入编辑器
3. 版本页行内打开、只读、发布、对比、克隆
4. 发布校验错误弹窗、点击定位、发布确认与 409
5. 工作流软删除、活跃 run 409；已发布版本不提供单独物理删除入口，历史任务仍可打开

**F2b 编辑器核心**

1. Graph DTO、`@xyflow/react` 适配、坐标还原和旧数据布局
2. 六类节点、拖拽新增、删除、类型切换、撤销/重做
3. 连线规则、条件/并行/打回视觉、扇出双向互斥；普通节点多前向入边必须显式 join，终验仅零或一条回边
4. 节点与边属性表单，岗位/员工使用 `/api/options/*` 脱敏数据源，工位使用团队 seats 接口
5. dirty、显式保存、只读、离开提醒、派生草稿

**F2c 高级编辑与校验**

1. 条件构建器、JSON 双向同步、懒加载 CodeMirror
2. prompt 变量插入、未知变量提示、实时预览
3. 前端校验、后端校验合并、错误清单定位
4. 保存 `{graph,revision}`、成功后 revision +1；409 展示服务端 revision，重新加载/force 覆盖路径、快捷键作用域
5. 前端双版本 diff 与字段级明细

**阶段门禁**

- 完整通过交互稿第 16 节验收清单
- 非法 JSON 不丢规则；Ctrl+S/Ctrl+Z 不串用画布与 CodeMirror 状态
- 后端校验是发布权威，前端校验不替代服务端
- 编辑器、CodeMirror、React Flow 不进入控制台首屏主包

### F3：任务中心、审批与产物

1. 三 Tab 列表、筛选、角标、状态标签
2. 我的工作三块：可认领、已认领、待我补充
3. 独立任务详情、节点时间线、当前 run 操作卡
4. 概览/变量/产物/事件页签
5. 新建自由任务/已发布工作流任务：本人创建即启动，指定他人校验 `task_dispatch`；成功进入详情，不实现草稿页或 `/advance`
6. 认领 CAS、409 刷新；提交结果必填、Markdown/JSON 校验、attempt_no
7. 扇出按 `fanout_group + fanout_slot` 展示独立 attempt；join 显示 missing，发起人或超管可确认范围并显式重跑 join
8. 终验通过/驳回、驳回意见必填、或签提示；零回边驳回显示 `approval_rejected`，一回边进入重做
9. 超时升级状态与 `escalation_resolve` 处理入口
10. 产物上传、预览、下载、过期重签；签名上传 URL 24h、单文件 100MB，内联产物单文件 5MB、总计 10MB；外部 Agent 只引用上传后的 artifact_id，不提交 type=url
11. 取消任务与四类终止原因；SSE 局部刷新和断线降级

**阶段门禁**

- 重复点击认领/提交不会重复写入；stale attempt 返回 409 后刷新详情
- 他人任务、非当前执行人、无权限用户看不到提交入口
- 列表与详情在 SSE 更新后不整页闪烁、不丢失正在编辑的结果
- 产物上传期间不可提交；取消任务显示四类终止原因；missing 分片补完不会自动重跑 join，显式重跑产生新 attempt 和范围记录

### F4：消息、追迹、概览与指标

1. 消息流筛选、详情抽屉、发送消息、实时插入
2. 任务追迹聚合时间线和事件过滤
3. 概览改版，复用健康状态和真实 overview 数据
4. 固定指标卡、趋势图、工作流/Agent 排行
5. 7/30 天/自定义筛选与 CSV 导出

**阶段门禁**

- 消息新事件高亮但不打断当前详情阅读
- 指标空数据不绘制误导性零线；口径提示完整
- CSV 使用当前筛选条件、UTF-8 BOM，并遵循服务端数据范围
- 图表无新运行时依赖，键盘可读表格数据

### F5：协同大屏、孪生展示、审计、集成、技能包与设置

1. 自动登记屏幕接管：屏幕列表、三种布局配置、自定义布局可视化编辑、草稿/发布、内嵌预览、全屏入口和远程定向聚焦；`screen_id/secret` 设备级持久化（`localStorage`），服务端只存哈希、明文仅登记返回一次；发布后 30 秒内推送
2. `/twin` 默认匿名 kiosk：隐藏侧栏/名册/抽屉/页脚，保留楼层切换与状态图例；登录可切交互模式发起任务，数据取屏幕绑定团队与本人 `data_scope` 的交集，空闲 5 分钟退回 kiosk；主题 auto/dark/light、任务状态与并发角标、结对线与气泡、断线重连和 429/503 降级；`paused` 仅停新配置，实时数据继续
3. 审计筛选、JSON diff、CSV；告警列表与确认
4. 通知规则 CRUD、同规则同资源通知冷却秒数、测试发送；展示 webhook/邮件重试失败审计，恢复不发通知
5. 集成四块改版；技能包沿用现有业务能力并迁移新设计系统
6. 设置向导三步保留且均可跳过，记录完成时间；重复进入不强制引导，完成后展示三张后续引导卡

**阶段门禁**

- 3D 预览只在可见时挂载，离开页面释放 renderer；自定义布局编辑器复用 SVG 舞台，不新增拖拽依赖
- 在线屏幕删除 409、`grid` 未绑定团队 422、聚焦目标离线 409、公开登记 429、SSE 满 503 均有独立状态
- 匿名 `/twin` 不请求需登录接口，公开投影字段白名单中不出现 `employee_id / agent_id / team_id / endpoint / token`，也不出现团队名称 `team`；交互模式无 `task_create` 发起任务显示 403
- 关闭浏览器或设备重启后凭 `localStorage` 复用 `screen_id/secret`；本地记录丢失时按新屏登记，不覆盖旧屏配置；登记响应之外任何接口都不回显 `secret`
- 交互模式数据 = 屏幕绑定团队 ∩ 本人 `data_scope`；屏幕未绑定团队时按本人范围
- `?preview=1` 不登记、不发心跳、不接收聚焦；只清理未接管的自动屏
- 交互模式连续 5 分钟无操作退回 kiosk，退出登录立即清除交互界面
- `auto` 主题跨 19:00/06:00 自动切换；`prefers-reduced-motion` 关闭走动人、脉冲与气泡动画
- 自定义布局保存后，管理端预览与 `/twin` 已发布效果一致
- 审计 diff 字段级高亮，大 JSON 不阻塞整页
- 通知规则测试发送有明确成功/失败结果，不伪造成功
- 屏幕离线、删除冲突、集成调用失败均有独立状态

### F6：真实接口切换与旧版清理

1. 按领域逐一关闭 mock，执行真实接口契约验收
2. 修复 DTO、错误码、空数组/null、时间格式等联调差异
3. 删除旧 Staff/Teams/Approvals 独立实现和无引用旧组件
4. 删除旧平铺导航、旧权限分支、旧节点名称文本建版入口
5. 更新所有测试，执行全量浏览器验收与构建检查
6. 与后端 Phase 2 及迁移同批发布，不单独上线前端破坏性改造

---

## 6. 页面与组件落点对照

| 页面 | 主要组件 | 阶段 |
|---|---|---|
| 概览 | 现有概览区块 + `ConsolePageState` | F4 |
| 指标与报表 | `MetricCard`、SVG TrendChart、BreakdownTable、CsvExportButton | F4 |
| 任务中心 | TaskTable、MyWorkBoard、TaskFilterBar | F3 |
| 任务详情 | TaskTimeline、CurrentRunCard、ResultSubmitDialog、ApprovalCard、ArtifactList | F3 |
| 消息与追迹 | MessageTable、MessageDrawer、TaskTraceTimeline | F4 |
| 协同大屏 | ScreenList、ScreenConfigForm、ScreenPreview、LayoutEditor（office/grid/custom）、FocusTargetPicker | F5 |
| 孪生展示 | TwinStage、TwinFloorTabs、TwinLegend、PairLayer、BubbleLayer（复用 `src/twin/`） | F5 |
| 组织 | EmployeeTable/Drawer、PositionMasterDetail、RoleDrawer、TeamSeatBoard | F1 |
| 工作流列表 | WorkflowCardGrid、WorkflowTemplateDialog | F2a |
| 工作流版本 | VersionTable、PublishValidationDialog、CloneDraftDialog | F2a |
| 编辑器/diff | 交互稿第 15 节全部组件 | F2b/F2c |
| 技能包 | 现有技能包组件迁移 | F5 |
| Agent 与接入 | AgentCardGrid/Drawer、InviteTable、InviteCreateDialog、InviteSnippetDialog | F1 |
| 集成 | 集成列表、调用调试、插件、运行配置 | F5 |
| 审计与告警 | AuditTable/DiffDrawer、AlertTable、AlertRuleDrawer | F5 |
| 设置向导 | 三步表单 + NextStepCards | F5 |

---

## 7. Mock 设计与接通顺序

### 7.1 实现方式

- 默认真实 API；仅 `DEV` 且 `VITE_API_MODE=mock` 时动态加载 `src/mocks/`
- mock 复用 `ApiResult`、HTTP 状态和错误结构，不在页面组件里写假数据
- fixture 使用固定 ID、固定时间，保证测试与截图可重复
- 内存数据支持增删改和冲突场景；刷新页面可重置
- 生产构建不加载 mock；发布验收必须显式使用真实模式

### 7.2 场景

```text
ready             有效登录、完整基础数据
empty             各列表空态
readonly          只读员工
supervisor        主管 + team 数据范围
denied            无权限直达
unavailable       服务不可用与恢复
conflict          认领/revision 保存/工位/软删除 409
expired           401、真人邀请与 Agent 邀请码 410、下载 URL 过期
stream-lost       SSE 断线、重连、轮询降级
```

### 7.3 mock 接通顺序

| 顺序 | 领域 | 目的 |
|---|---|---|
| M0 | bootstrap、identity/me、权限模板、tasks/summary | 先稳定登录、导航和四种身份 |
| M1 | employees、positions、roles、teams/seats、options、agents、agent-invites、endpoint 审批 | 提供全站岗位/员工/角色引用数据与接入审批 |
| M2 | workflows、versions、graph、validate、clone、publish | 编辑器可独立完整开发 |
| M3 | tasks、runs、fanout_slot、claim、result、cancel、rerun-join、approvals、artifacts、事件流 | 打通自由任务、执行、汇聚与 HITL 主闭环 |
| M4 | messages、trace、overview、metrics/export | 打通只读分析与追迹 |
| M5 | collab screens（公开登记/心跳/配置/发布/聚焦/离线）、三种布局、`/twin` 匿名 kiosk 与登录交互模式、公开 SSE、audit、alerts/rules、integrations、skills、setup | 覆盖大屏、孪生与系统运维页面；公开 fixture 不依赖登录，交互 fixture 覆盖 403 与 5 分钟退回 |

M5 的公开大屏 fixture 必须同时覆盖：自动登记成功、在线删除 409、`grid` 未绑定团队 422、聚焦目标离线 409、公开登记 429、SSE 503 与断线重连；交互模式覆盖无 `task_create` 的 403 和空闲退回 kiosk。

每个领域真实接口完成后，以“同一用例分别跑 mock 与 real”为准切换，不一次性盲切全部页面。

---

## 8. 测试与验收方案

### 8.1 测试基础

- 保留 Vitest 与现有 SSR smoke 测试
- 增加开发依赖：`jsdom`、`@testing-library/react`、`@testing-library/user-event`
- 增加脚本：`typecheck = tsc --noEmit`
- React Flow 的算法与序列化主要做纯函数测试；少量画布交互做浏览器验收，避免 jsdom 模拟 SVG 布局造成假通过

### 8.2 必测纯函数

| 模块 | 用例 |
|---|---|
| permissions/navigation | 21 权限点、四模板、空组隐藏、console_admin 与 `*` |
| graph | Graph 往返序列化、revision 冲突/覆盖、坐标、旧节点补布局、非法边、显式 join 与终验回边 |
| condition | 构建器/JSON 往返、非法 JSON、嵌套 AND/OR、字段白名单 |
| diff | 新增/删除/修改节点和边、字段级变化、稳定顺序 |
| layout | BFS 分层、回边、孤立节点、无坐标旧图 |
| promptVars | 已知变量、未知变量、光标插入、预览替换 |
| tasks | 状态文案、本人创建即启动/代派权限、自由任务当前 run、fanout_slot、join 重跑、attempt 冲突、四类终止原因 |
| CSV | 中文 BOM、引号/换行转义、筛选参数传递 |
| SSE | 分帧、心跳、重连、坏 JSON、重复事件 |

### 8.3 关键 DOM 交互

- 导航权限与直接访问 403
- Drawer/Dialog 焦点、Esc、关闭后焦点返回
- 员工权限模板套用后仍可微调
- 认领 409、revision 保存 409、工位 409、活跃 run 软删除 409
- 真人邀请已撤销/过期/已使用返回 410；Agent 邀请已使用 409、撤销/过期 410；endpoint 待审批不派单
- 提交结果必填、JSON 错误、上传中禁用；外部产物只使用 artifact_id
- 审批驳回意见必填
- Tab/筛选写 URL，前进后退可恢复

### 8.4 浏览器主路径

1. 四种身份登录与导航
2. 邀请真人并调整权限
3. 生成 Agent 邀请码、复制三种接入片段、作废
4. 岗位绑定角色与员工、工位拖拽冲突
5. 从四模板创建工作流
6. 编辑图、条件双模式、扇出互斥、显式 join、终验回边、prompt 预览
7. 校验定位、revision 保存冲突与 force 审计、离开提醒、发布与版本 diff
8. 本人自由任务创建即启动、代派权限、认领共享待办、提交结果与产物、stale attempt
9. 扇出 missing 补完与显式 join 重跑、终验通过/两种驳回路径及或签关闭
10. 消息发送、任务追迹、指标导出
11. 告警规则测试发送
12. `/twin` 自动登记与匿名 kiosk、登录交互模式、三布局切换、草稿/发布、主题自动昼夜、并发角标、结对气泡、定向聚焦
13. 在线删除 409、`grid` 未绑定 422、离线聚焦 409、公开登记 429、公开 SSE 503 与退避重连
14. SSE 断线恢复、1024/1280 布局、键盘操作

### 8.5 每阶段命令门禁

```text
npm run typecheck
npm test
npm run build
```

构建后还需以 `vite preview` 做真实 API smoke，防止仅在 dev proxy 下可用。

---

## 9. 构建与性能

- 主包：React、路由、公共 ConsoleKit 和轻量页面
- 独立 chunk：`xyflow`、`codemirror`、`three/twin`
- React Flow CSS 只在编辑器相关 chunk 引入，并用暗色 token 覆盖
- CodeMirror 在切换 JSON 模式时加载，不在打开属性面板时加载
- 3D 预览仅当前屏幕且页面可见时渲染；离开即释放
- 大列表先使用分页/限量，不在本期引入虚拟列表依赖
- 大 JSON diff、追迹时间线采用折叠与分段渲染，避免一次展开全部内容
- 所有请求在页面卸载后取消或忽略结果，避免竞态更新

---

## 10. 需求追踪

| 需求稿章节 | 实施阶段 | 核心验收 |
|---|---|---|
| 1 信息架构 | F0、F6 | 5 组导航、13 页面、重定向、fluid |
| 2 权限矩阵 | F0、F1 | 四身份、21 权限、页面/按钮/数据范围 |
| 3 任务中心 | F3 | 本人创建即启动/代派、自由任务、认领、扇出/join、结果、终验、升级、产物、实时与冲突 |
| 4 工作流列表/版本 | F2a | 卡片、模板、版本操作、删除冲突、校验弹窗 |
| 5 组织 | F1 | 员工双 Tab、抽屉、岗位、角色、工位 |
| 6 大屏/消息/指标/审计 | F4、F5 | 双 Tab、导出、告警与通知规则 |
| 7 Agent/集成/设置 | F1、F5 | 卡片、邀请片段包、长期邀请码、引导卡 |
| 编辑器交互稿 | F2b/F2c | 第 16 节全部条目 |

---

## 11. 最终完成定义

- 所有页面使用真实接口，生产运行不依赖 mock
- 普通员工到超管的导航、按钮、直达路由与数据范围全部符合权限矩阵
- 工作流编辑器交互稿第 16 节全部通过
- 任务创建/启动、认领、扇出分片、显式 join 重跑、结果提交、终验、产物和 SSE 断线恢复形成完整闭环
- 邀请码明文不明文持久化；token 仅以密文与不可逆 lookup digest 持久化、不写日志；endpoint 审批及撤销/过期/冲突状态可验证
- `/twin` 匿名 kiosk 与登录交互模式、`/console/collab` 共用屏幕表；三布局、草稿/发布、定向聚焦、在线删除 409、429/503 降级均可验证，公开投影不出现内部 ID
- 旧独立页面和旧导航已删除，旧书签重定向有效
- 无未处理 Promise、明显控制台错误、请求竞态和死链接
- 所有列表使用统一包装、所有 JSON 时间使用 ISO UTC、组织/选项路径无旧契约回退，Graph revision 与 force 审计一致
- `typecheck`、全部测试、生产构建、preview 真实接口 smoke 全通过
- 与后端权限改名、DAG/API 和数据库迁移同批上线

---

## 12. 实施时的建议提交边界

以下仅作为代码审查边界，不要求在本计划阶段创建提交：

1. `frontend-foundation`：依赖、门禁、权限、导航、布局、公共组件、测试基础
2. `organization-and-agent-access`：组织四 Tab、Agent 卡片、邀请码
3. `workflow-list-versions`：卡片、模板、版本页、发布校验
4. `workflow-editor-core`：图、节点、边、属性、保存与离开
5. `workflow-editor-advanced`：条件、prompt、校验、diff、快捷键
6. `task-center`：列表、详情、认领、结果、审批、产物、实时
7. `messages-and-metrics`：消息、追迹、概览、指标与导出
8. `operations-pages`：大屏、审计告警、集成、技能包、设置
9. `real-api-cutover`：真实接口切换、旧代码删除、最终验收

每个边界都必须可独立构建和测试；不把“后续再补权限/错误态”留到最终清理阶段。
