# F1–F4 前端与冻结需求差异审计

> 2026-11-25 · v1.0（F1–F4 主体审计完成；技能包、集成、设置向导未逐行审计）
> 方法：逐页阅读实际代码，对照 [frontend-requirements.md](../design/frontend-requirements.md) 的已确认章节。
> 每条给出代码位置与需求出处。本清单只描述差异，不代表已修复。
> 背景：此前执行计划把 F1–F4 标为完成，本次审计用于校正该结论。
>
> **P0 修复回填（2026-11-25）**：下列明细保留首次审计时的代码证据。当前代码已修复工作流节点选择、已发布只读与派生跳转，任务新建、结果提交与审批处理，消息 `message.created` SSE 刷新，以及 Agent token 的 window 全局传递。任务产物上传契约缺口已补齐（Python/Java 双栈：`TaskDetailOut.artifacts` + `POST /api/tasks/{task_id}/nodes/{node_id}/artifacts`，前端产物 Tab 可列出/下载/上传，结果弹窗可挂载 `artifact_ids`）；新消息 2 秒高亮及其余未列明缺口尚未补齐；不得据此认定 F1–F4 全量完成。

## F1 组织页（需求 §5）

代码：[ConsoleOrganizationPage.tsx](../../web/src/pages/console/ConsoleOrganizationPage.tsx)、[org/api.ts](../../web/src/lib/org/api.ts)、[org/view.ts](../../web/src/lib/org/view.ts)

| # | 需求出处 | 代码现状 | 类型 |
|---|---|---|---|
| 1 | §5.1 员工内分「真人 / Agent」两个子 Tab | 只有 `useEmployees({ type: "human" })` 一个列表（L95），无 Agent 子 Tab | 缺失 |
| 2 | §5.2 列：姓名/岗位/角色数/技能数/权限模板/工位/状态/最后活跃 | 实际列为 ID/姓名/状态/类型/数据范围/在线/操作（L140-214） | 缺失 |
| 3 | §5.2 邀请弹窗含登录名、权限模板（默认员工） | 无登录名、无模板下拉；初始权限默认空数组（L646），需逐项手勾 | 缺失 |
| 4 | §5.2 生成一次性邀请链接，可复制 | 只展示邀请码文本（L712-721），没有可复制链接 | 部分 |
| 5 | §5.2 邀请可撤销、重发，旧链接 410 | `resendInvite` / `revokeInvite` 已在 api.ts 实现（L73-83）但页面无任何入口，也无邀请列表 | 缺失（含契约缺口：无邀请列表读取） |
| 6 | §5.4 档案含登录名、联系方式、入职时间；Agent 含 model/endpoint/channel_type | 档案只有姓名/数据范围/启用 + 只读状态/类型/Agent ID/名称/框架（L414-486） | 缺失 |
| 7 | §5.4 第四 Tab：团队、工位选择、联系人增删 | 只有团队与岗位两个下拉（L567-598），**没有工位选择**；联系人为占位提示（L600-607） | 缺失 + 占位 |
| 8 | §5.4 技能标签可增删，需 `role_bind` | 技能只读展示，文案写「由岗位/角色聚合」（L504-512），无编辑入口；保存按钮不校验 `role_bind` | 相反 |
| 9 | §5.4 权限 Tab：模板下拉 + 21 项 + data_scope，按可授权子集过滤 | 只有 21 项勾选，无模板、无 data_scope，未做授权上界过滤（L528-559） | 部分 |
| 10 | §5.4 权限 Tab 仅 console_admin 可改，其他人只读 | 非超管直接显示 forbidden 占位，连只读权限列表都看不到，与自身文案「当前标签页只读展示」矛盾（L520-526） | 相反 |
| 11 | §5.5 岗位右栏：说明、启用、绑定角色、候选员工、关联节点/run 数 | 右栏只有名称 + capabilities（L992-1042）；绑定接口 `bindPositionRoles/Employees` 已存在但未使用 | 缺失 |
| 12 | §5.5 左栏显示角色数、候选人数 | 左栏只有名称与能力标签（L975-988） | 缺失（依赖统计字段） |
| 13 | §5.10 新建岗位需 `org_manage` | `canManage = role_manage \|\| org_manage`（L907），权限放宽 | 相反 |
| 14 | §5.6 角色列表含技能数/绑定岗位数/员工数/更新时间；抽屉含绑定岗位、绑定员工 | 列表为名称/状态/描述/能力；抽屉只有名称/启用/描述/能力（L1276-1313），绑定接口未使用 | 缺失 |
| 15 | §5.7 团队列表含主管、成员数、在线数 | 只有名称与负责人 ID 前 8 位（L1449-1458），主管不显示姓名 | 缺失 |
| 16 | §5.7 工位网格、拖员工入座、拖回取消、409 提示 | 是工位列表 + 下拉分配（L1462 起），非网格也非拖拽；占用 409 无专门提示 | 部分 |
| 17 | §5.8 空态分「暂无真人 / 暂无 Agent」 | 统一「暂无员工」（L138） | 部分 |
| 18 | 红线：禁止手写 DTO、禁止 any 绕过 | 页面内 `SeatView` 手写类型（L1324-1331）；岗位/角色/团队保存用 `body: any`（L922、L1154、L1375）；`data_scope as any`（L327） | 违规 |

## F1 Agent 页（需求 §7.1）

代码：[ConsoleAgentsPage.tsx](../../web/src/pages/console/ConsoleAgentsPage.tsx)

| # | 需求出处 | 代码现状 | 类型 |
|---|---|---|---|
| 1 | §7.1 点击卡片打开 560px 详情抽屉：health_url、创建时间、token 指纹、上次轮转、健康检查与延迟、最近 5 条 run | 没有详情抽屉，只有轮转结果抽屉与注销确认（L271-302）；无健康检查入口 | 缺失 |
| 2 | §7.1 待审批期间显示「暂停新任务投递」；审批需查看旧/新地址与校验结果 | 列表只有待审批标签，批准/拒绝一键完成，无地址对比、无校验结果、无暂停投递提示（L206-223） | 缺失 |
| 3 | §7.1 外壳卡片含待办数、最后心跳、所属员工与岗位 | 表格无这三列（L144-266） | 缺失 |
| 4 | §7.1 token 不明文落界面与日志之外的地方 | 新 token 先写到 `window.__agent_token_buffered` 全局变量再由抽屉读取（L95、L309-312），应改为组件状态传递 | 违规/安全隐患 |
| 5 | §7.1 邀请码列：码前缀、员工名、岗位、创建人、创建时间、有效期、状态、使用人；支持查看详情 | 实际为 ID/类型/通道/数据范围/员工/过期时间/状态/操作（L380-440），无码前缀、岗位、创建人、创建时间、使用人，无详情 | 缺失 |
| 6 | §7.5 邀请码 Tab 仅 `console_admin` | `canCreate = consoleAdmin \|\| orgManage`（L347），且 Tab 对非超管可见 | 相反 |
| 7 | §7.1 生成弹窗：员工名、岗位、业务角色/技能、权限模板、有效期 1h/24h/7d/长期（默认长期） | 员工名是自由文本；**岗位字段写死为空**（`const [positionId] = useState("")`，L531，无输入入口）；无业务角色与模板；有效期是任意小时数输入，默认 24h（L529） | 缺失 + 死字段 |
| 8 | §7.1 权限与 data_scope 按授权上界过滤 | 未过滤，全部 21 项可勾（L737-774） | 缺失 |
| 9 | §7.1 三页签接入示例须真实可用 | 示例为前端硬编码（L788-831）：`python -m mailbus.mcp`、四个工具名、`POST /api/tasks/{task_id}/result` 与冻结契约 `POST /api/tasks/{id}/nodes/{node_id}/result` 不一致；curl 使用相对路径无 host | 未核实 + 与契约不符 |

## F1 已确认做得对的部分

- 域层 `org/api.ts` 全部使用生成类型，接口路径与 §5.9 一致；员工绑定、邀请撤销/重发的 API 封装已存在，只是页面没接。
- 员工移除有二次确认并透传 409；邀请码明文只在创建结果中展示一次。
- Agent token 轮转/吊销/解绑/注销按钮按 `console_admin`、`agent_deregister` 做了区分，注销 409 有处理。

## F2 工作流列表（需求 §4.1–4.5）

代码：[ConsoleWorkflowsPage.tsx](../../web/src/pages/console/ConsoleWorkflowsPage.tsx)

| # | 需求出处 | 代码现状 | 类型 |
|---|---|---|---|
| 1 | §4.2 新建从 4 个模板开始，创建后直接进入编辑器 | 只有名称输入，创建空工作流后仅刷新列表（L27-40、L167-193）；无模板、不跳编辑器 | 缺失 |
| 2 | §4.3 版本页 `/console/workflows/:id`：版本表格、只读查看、对比、克隆 | 没有版本页，只有卡片上的「编辑最新版 / 派生 / 发布 / 删除」（L123-160）；无对比 diff | 缺失 |
| 3 | §4.4 发布前先 validate，失败弹窗列错误并可跳编辑器定位；通过后二次确认 | 列表页直接调 publish（L57-69），不校验、不二次确认、无错误定位 | 相反 |
| 4 | §4.1 卡片含描述首行、节点数、最近更新时间、「有草稿待发布」状态；顶部搜索框 | 卡片只有名称/ID/最新版/创建时间（L109-122）；无搜索框 | 缺失 |
| 5 | §4.7 克隆需 `workflow_modify` | 派生按钮用 `canCreate`（L132） | 权限错配 |
| 6 | 公共组件规范 | 删除用 `window.confirm`（L43）而非 ConfirmDialog | 一致性 |

## F2 工作流编辑器（需求 §4.3、§4.4 + workflow-editor-ux）

代码：[WorkflowEditorPage.tsx](../../web/src/pages/console/WorkflowEditorPage.tsx)

| # | 需求出处 | 代码现状 | 类型 |
|---|---|---|---|
| 1 | §4.3 已发布版本只读，编辑时派生草稿 | `isPublished` 只用于显示标签（L277、L296），画布与属性仍可编辑并保存到已发布版本 | 相反（严重） |
| 2 | 基本交互：点击节点编辑属性 | `selectedNode` 只在「新增节点」时设置（L119），ReactFlow 没有 `onNodeClick`，点击已有节点不会打开属性面板 | 功能缺陷（严重） |
| 3 | 条件构建器、JSON 同步、变量提示 | 边的 condition 只能来自 `e.label`（L157），没有任何编辑入口 | 缺失 |
| 4 | 属性表单走 `/api/options/positions` | 岗位是手填文本框 `positionId`（L493-502） | 缺失 |
| 5 | 连线规则：六类节点、条件/并行/打回、扇出互斥、显式 join、终验零/一回边 | `onConnect` 无任何校验（L87-93），注释声称的规则未实现；扇出无配置 UI | 缺失 |
| 6 | 派生草稿可用 | `cloneLatest` 成功后只执行 `window.location.hash = ""`（L253-258），不跳转、不刷新、无提示；项目用 BrowserRouter | 功能缺陷 |
| 7 | dirty 离开拦截 | 未做，`useBlocker` 未使用 | 缺失 |
| 8 | 发布先校验 + 二次确认 | 编辑器同样直接 publish（L237-250） | 相反 |
| 9 | 校验失败点击错误定位节点 | 只拼接文本（L232），不能定位选中 | 缺失 |
| 10 | 禁止 any 绕过生成类型 | `toFlowNode(n: any)` 同时猜两套字段名（L584-601）、`data as any` 多处、`(result.data as any).revision`（L178） | 违规 |

编辑器已做到的：React Flow 画布、六类节点新增、连线增删、Graph 读写、revision CAS 与 409 强制覆盖/重新拉取、手动校验按钮。

## F3 任务列表（需求 §3.1–3.3、§3.8）

代码：[ConsoleTasksPage.tsx](../../web/src/pages/console/ConsoleTasksPage.tsx)

| # | 需求出处 | 代码现状 | 类型 |
|---|---|---|---|
| 1 | §3.1 新建任务：自由任务/已发布工作流，创建即启动并进详情 | 页面没有「新建任务」入口 | 缺失（核心） |
| 2 | §3.10 审批走 `GET /api/approvals` + `POST /api/approvals/{id}/resolve` | 审批 Tab 只是用 `state=approval` 过滤任务列表（L53），未接审批接口 | 相反 |
| 3 | §3.1 路由 `?tab=approvals` | 实现用 `?tab=approval`（L19），与需求及旧地址重定向不一致 | 不一致 |
| 4 | §3.2 状态 pending/running/blocked/done/cancelled/failed，且不提供草稿任务 | 筛选项含 draft/queued/waiting/approval 等旧状态（L22-33） | 相反 |
| 5 | §3.3 我的工作分可认领/我已认领/待我补充三块 | 只是 `owner_id=本人` 的同一张表（L52） | 缺失 |
| 6 | §3.2 列含当前节点；筛选含关键词、状态多选、时间范围 | 无当前节点列；负责人/流程靠手输 ID；无关键词与时间范围；状态单选（L207-249） | 部分 |
| 7 | §3.4 取消：发起人或超管可见 | 列表与详情都用 `task_dispatch`（L183） | 权限待核对 |
| 8 | §3.8 SSE 局部刷新 + 断线 30s 轮询 | 只有手动刷新按钮 | 缺失 |
| 9 | §3.1 角标：我的=可认领+已认领未完成 | 只用 `summary.mineOpen`（L68），未含可认领 | 待核对 |

## F3 任务详情（需求 §3.4–3.9）

代码：[ConsoleTaskDetailPage.tsx](../../web/src/pages/console/ConsoleTaskDetailPage.tsx)

| # | 需求出处 | 代码现状 | 类型 |
|---|---|---|---|
| 1 | §3.5 提交结果弹窗：Markdown/JSON 切换、必填、拖拽上传产物、≤100MB | 用 `window.prompt("输入节点运行结果（字符串）", "done")`（L123），可一键提交 "done" | 相反（严重） |
| 2 | §3.4 仅当前 run 属于我且 running 时显示提交入口 | 每个有 run 的节点行都显示「提交结果」，只校验 `result_submit`（L381-390） | 相反 |
| 3 | §3.6 审批卡片：申请内容、变量、历史意见、通过/驳回、或签提示 | 完全没有审批处理 UI | 缺失 |
| 4 | §3.4 左节点时间线 + 右粘性操作卡，节点可点击切换，显示结果摘要与产物数 | 是节点表格 + Run 表格，无选中交互、无产物数 | 部分 |
| 5 | §3.4 parallel_join 显示前驱终态与 missing 分片；重跑汇聚仅发起人或超管 | 只有 fanout_group 文本与 rerun-join 按钮，权限挂在 `result_submit`（L391-400） | 缺失 + 权限错配 |
| 6 | §3.8 详情页订阅 task.updated / artifact.updated | 无订阅，操作后手动 refresh | 缺失 |
| 7 | §3.9 403 整页无权限、404 任务不存在、服务不可用黄条 | 统一「加载失败」+ 返回列表（L167-180） | 缺失 |
| 8 | §3.7 产物列表与内联预览、24h 签名下载 | 已修复：`TaskDetailOut.artifacts` + `POST /api/tasks/{task_id}/nodes/{node_id}/artifacts`；产物 Tab 列出/下载/上传，结果弹窗可勾选挂载 `artifact_ids` | 已修复 |
| 9 | §3.4 变量表 task_variables，来源 input/system | 变量 Tab 为占位（L471-485） | 占位（契约缺口） |

详情页已做到的：元信息、终止原因展示、节点与 Run 列表（attempt/fanout/耗时/结果）、trace 时间线、认领与取消的 409 处理、rerun-join 二次确认。

## F4 消息（需求 §6.2）

代码：[ConsoleMessagesPage.tsx](../../web/src/pages/console/ConsoleMessagesPage.tsx)、[message/hooks.ts](../../web/src/lib/message/hooks.ts)

| # | 需求出处 | 代码现状 | 类型 |
|---|---|---|---|
| 1 | §6.2 双 Tab：消息流 + 任务追迹 | 只有消息流，任务追迹未做 | 缺失 |
| 2 | §6.2 实时订阅 `message.created`，新消息高亮 2 秒 | `useLiveMessages` 只监听 window 自定义事件 `mailbus:message`（hooks.ts L123-127），**全工程没有任何地方 dispatch 该事件**，实时刷新实际不会发生；也没有 SSE 订阅和高亮 | 相反（声称有但实际无） |
| 3 | §6.2 筛选项：通道 web/a2a/file_bus、类型 message/command/task_assignment/task_cancel、方向、时间 | 通道选项为 file_bus/a2a/mcp；类型是自由文本；无方向与时间筛选（L25-26、L131-147） | 不一致 |
| 4 | §6.2 详情含 payload、附件、关联任务跳转 | 只有基础字段与正文 + trace（L227-270） | 部分 |
| 5 | §6.2 发送选接收员工与类型 | 接收人手输 ID，类型自由文本默认 `note`（不在需求类型集合内） | 部分 |
| 6 | 需求未提供删除消息 | 列表有删除按钮，权限挂在 `system_config`，无二次确认（L204-219） | 多余 + 权限错配 |
| 7 | 类型安全 | 列表/详情大量使用 `row: any`，未消费 view 映射 | 违规 |

## F4 审计与告警（需求 §6.4）

代码：[ConsoleAuditPage.tsx](../../web/src/pages/console/ConsoleAuditPage.tsx)、[ConsoleMetricsPage.tsx](../../web/src/pages/console/ConsoleMetricsPage.tsx)

| # | 需求出处 | 代码现状 | 类型 |
|---|---|---|---|
| 1 | §6.4 双 Tab：审计日志 + 告警，另有通知规则子页签 | 审计页只有日志；告警列表、确认/恢复、通知规则新建编辑、测试发送全部未做。契约里 `/api/alerts`、`/api/alert-rules` 存在但未被使用 | 缺失 |
| 2 | §6.4 审计列含结果、IP；筛选含结果 | 列为 #/操作人/动作/资源/明细/时间（L127-164） | 缺失 |
| 3 | §6.4 详情为变更前后 JSON 字段级 diff 高亮 | 只 `JSON.stringify(detail)`（L184-191） | 缺失 |
| 4 | §6.4 审计导出 CSV | 无导出入口 | 缺失 |
| 5 | §6.4 权限：告警与通知规则 `console_admin` | 告警规则被放在指标页，只有启用/停用，权限 `system_config`（Metrics L296-344） | 位置与权限均不符 |

## F4 指标（需求 §6.3）

| # | 需求出处 | 代码现状 | 类型 |
|---|---|---|---|
| 1 | §6.3 趋势：任务创建/完成、平均节点时长 | 只请求 `messages.total`（L122-127） | 不符 |
| 2 | §6.3 排行：工作流完成率与平均时长、Agent 负载与失败率 | 只请求 `messages.by_kind`（L128） | 不符 |
| 3 | §6.3 指标口径用问号提示说明 | 以 manifest 原始 JSON 展示（L347-353），非口径提示 | 部分 |
| 4 | §6.3 空态与加载骨架 | 加载为文本，无骨架 | 部分 |
| 5 | §6.3 指标卡八项 | 由后端 `cards` 驱动渲染，是否覆盖八项需联调确认 | 待联调 |

## F4 概览（需求 §1、概览快照）

[ConsoleOverviewPage.tsx](../../web/src/pages/console/ConsoleOverviewPage.tsx) 已改用生成的 `OverviewOut`，功能符合；但仍在组件内直接 `api()` 并手写 health 响应类型（L11、L19-20），未走域 hooks，属违规而非功能缺口。

## 路由与系统页

[ConsoleApp.tsx](../../web/src/pages/console/ConsoleApp.tsx)：

- 没有 `/console/workflows/:workflow_id` 版本页路由，该地址会被通配路由重定向回 `/console`（L196-204、L249）。
- 旧地址 `/console/approvals` 重定向到 `?tab=approvals`，而任务页实际 Tab key 是 `approval`（L248）。
- 技能包、集成、设置向导仍是改版前页面，本次未逐行审计；集成页自述动作调用与重载为占位，设置向导的「接下来」卡片未确认。

## 横切问题

1. **`any` 与手写 DTO 回潮**：组织、Agent、工作流编辑器、消息、审计、指标、任务详情都存在；F0 立的「生成类型唯一来源」在执行中没被守住。
2. **页面文案与真实行为不符**：消息页宣称 SSE 实时插入、编辑器注释宣称连线规则、组织权限 Tab 宣称只读展示，均与代码不符。
3. **权限点使用不一致**：克隆、取消任务、rerun-join、邀请码、岗位管理、消息删除多处与 §2.5/§5.10/§7.5 对不上，需要一次集中的权限对照。
4. **公共组件未被统一使用**：`window.confirm` / `window.prompt` 仍在关键写操作中。
5. **mock 与真实契约脱节**：`/api/public/layout` mock 返回空楼层，导致大屏在 mock 下无法验证；消息实时、任务变量与产物等也没有可用 mock 场景。

## 最严重的 8 个问题（建议优先）

1. 工作流编辑器：点击已有节点无法打开属性面板（功能缺陷）。
2. 工作流编辑器：已发布版本可直接编辑保存，没有只读与派生约束。
3. 任务详情：提交结果用 `window.prompt`，可一键提交 "done"，无附件、无 JSON 校验、无归属判断。
4. 任务中心：没有新建任务入口；审批未接 `/api/approvals`，无通过/驳回。
5. 消息中心：宣称的实时刷新实际不会触发。
6. Agent 页：新 token 经 window 全局变量传递；生成邀请码的岗位字段写死为空。
7. 组织页：权限编辑不做授权上界过滤，技能不可编辑，岗位/角色绑定关系没有 UI。
8. 告警与通知规则整体缺失，审批中心整体缺失。

## 需要后端契约配合的缺口（前端无法独自补齐）

| 缺口 | 影响 |
|---|---|
| 任务详情缺 `task_variables` / 上下文 / artifacts 列表 | 详情变量与产物 Tab 只能占位 |
| 真人邀请列表/详情读取 | 邀请管理、撤销重发入口无法落地 |
| 员工联系人读写 | 抽屉第四 Tab 占位 |
| 岗位/角色的关系统计（角色数、候选人数、员工数、节点数、run 数） | 列表与右栏统计列缺失 |
| Agent 详情补充 token 指纹、轮转时间、健康延迟、最近 run、待办数 | 详情抽屉无法完整实现 |
| 大屏草稿读取、重命名、grid/custom 结构 | 见 [collab-screen-contract-proposal.md](./collab-screen-contract-proposal.md) |

## 对既有文档的校正建议

- `frontend-execution-plan.md`：F1–F4 的复选框多数与实际不符，建议按本清单回退为部分完成，并链接本文件。
- `smoke-checklist.md`：§2–§7 部分条目写的是需求行为而非现状（如员工搜索、邀请撤销、发布校验定位、提交结果弹窗、消息 SSE、告警规则），联调前应按修复后的实现重写，不能拿它当现状验收。

