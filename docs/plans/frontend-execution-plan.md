# 前端执行计划

> 2026-11-25 · v1.1（按 4 项结构决策重写）
> 主计划：[frontend-implementation-plan.md](../design/frontend-implementation-plan.md)（F0–F6）
> 需求：[frontend-requirements.md](../design/frontend-requirements.md)、[workflow-editor-ux.md](../design/workflow-editor-ux.md)
> 后端：[backend-execution-plan.md](./backend-execution-plan.md)
> 范围：`web/`；**不改 `python/`、`java/`、迁移 SQL**。

---

## 0. 单一驱动链与类型来源

| 层 | 唯一来源 | 规则 |
|---|---|---|
| 接口契约 | `shared/contracts/generated/openapi.json` | 后端导出，前端只读 |
| TS 类型 | 由 OpenAPI 生成到 `web/src/lib/contracts.ts` | **禁止手写 DTO**、禁止 `any` 绕过 |
| 视图模型 | `lib/<domain>/view.ts` | 只做展示映射，不新增服务端字段 |
| 请求 | `lib/<domain>/api.ts` | 组件不得直接 `fetch` |
| 数据 | `lib/<domain>/hooks.ts` | 统一 AbortController、加载/空/错状态 |

**落地方式**：新增 **devDependency** `openapi-typescript`（不属于运行时依赖，不违反现有约束），脚本 `npm run gen:types` 生成 `web/src/lib/contracts.ts`；CI 执行生成并 `git diff --exit-code`，禁止契约漂移。

**生成时机**：必须等后端 **B1.5 契约桩**导出后再生成本地 `contracts.ts`；**禁止用 Phase 1 OpenAPI 生成**。在 B1.5 前，F0 只允许手写 3 个临时通用类型（`ApiError`、`Page<T>`、`Ok`），领域 DTO 一律不手写。

**字段账本**：[contract-matrix.md](./contract-matrix.md) 是页面/按钮 → 接口 → DTO → 表列的唯一登记处；前端不得新增矩阵外字段，公开端只消费白名单视图模型。

> 注意：DDL 不直接被前端消费。真实链路是「DDL 冻结 → 后端 DTO → OpenAPI → TS 生成」；前端只认最后一步。

---

## 1. 防重复红线（任一违反即不通过）

1. 一个领域只有一个 `api.ts`、一个 `hooks.ts`；页面不得内联请求。
2. 一个能力只有一个实现：

| 能力 | 唯一落点 | 禁止 |
|---|---|---|
| 屏幕身份（登记/持久化/心跳） | `lib/screen-identity.ts` | TwinPage 与 ConsoleCollabPage 各写一套 |
| SSE 订阅/重连 | `lib/events.ts` | 保留第二套 `twin/stream.ts` 实现 |
| 布局舞台渲染 | `components/twin/TwinStage.tsx` | 管理端预览与 `/twin` 各写一套 SVG |
| 权限判断 | `lib/permissions.ts` 的 `can()` | 页面自行判断 `permissions.includes` |
| 错误处理 | `lib/api.ts` 统一映射 | 每个页面自写 409/410/429 分支 |
| 表单校验 | 领域 `schema.ts` | 弹窗与页面各写一份 |

3. 公开端只消费白名单视图模型，不直接使用 Admin DTO 再删字段。
4. mock 必须导入生成的类型，禁止另建 mock DTO。
5. 组件不得复制另一组件的字段列表；公共字段沉到 Base 组件或 view 映射。

---

## 2. 数据层规范

- 每个域提供 `useXxxList()` / `useXxxDetail()`，内部负责 AbortController 与竞态丢弃。
- 组件只拿 `{ data, loading, error, refresh }`，不感知 URL 与 DTO。
- 不引入全局缓存库；跨页共享只允许：
  - 当前登录身份与权限（`console-access`）
  - 屏幕身份（`screen-identity`）
  - 导航角标（由 `task.updated` 事件刷新）
- 写操作统一走 `api.ts`，错误按 400/401/403/404/409/410/429/0/5xx 映射，页面只处理业务文案。
- SSE 只在任务详情、消息、大屏三处订阅，销毁时关闭；断线 30s 轮询仅任务页启用。

---

## 3. 与后端同域节奏（按域交错）

| 后端域 | 前端阶段 | 前端开始条件 |
|---|---|---|
| B2 组织 | F1 组织 | 该域 OpenAPI 导出且 TS 已生成 |
| B3 工作流 | F2 | Graph 契约冻结 |
| B4 任务 | F3 | claim/result/cancel/join 契约冻结 |
| B5 Agent/A2A | F1 Agent 部分 | endpoint/邀请契约冻结 |
| B6 大屏 | F5 | 035/036 完成、公开 API 冻结 |
| B7 指标等 | F4 | 指标/审计契约冻结 |

> 前端不等“后端全部完成”，但也不在契约冻结前写真实请求；未冻结部分只能用同构 mock。

---

## 4. 当前代码必须优先修改（审计结论）

| 文件 | 现状 | 目标 |
|---|---|---|
| [TwinPage.tsx](../../web/src/twin/TwinPage.tsx) | `sessionStorage` 存屏幕身份 | 迁到 `lib/screen-identity.ts`，用 `localStorage["mailbus.screen"]` |
| [ConsoleCollabPage.tsx](../../web/src/pages/console/ConsoleCollabPage.tsx) | 复制一套登记/存储逻辑 | 改为调用同一 `screen-identity` |
| [collab.ts](../../web/src/twin/collab.ts) | body 传 `secret` | 改 `X-Screen-Secret` 头 |
| [stream.ts](../../web/src/twin/stream.ts) | SSE 实现 | 并入 `lib/events.ts`，旧文件改为薄包装或删除 |
| 公开投影渲染 | 可能渲染团队 | 只渲染白名单字段，不含 `team` |

---

## 5. 阶段任务

### F0：驱动链、门禁与基础设施

- [x] 接入 `openapi-typescript` 与 `gen:types:check` diff 校验；**生成必须等后端 B1.5 契约桩导出**，不得用 Phase 1 OpenAPI 生成。
- [x] `lib/api.ts` 统一路径、分页包装、UTC、错误结构、FormData、下载重签。
- [x] `console-access` 放开登录员工；`permissions.ts` 21 权限；`navigation.ts` 5 组。
- [x] `RequirePermission` 与统一 403/404/空态/骨架屏。
- [x] 分组侧栏、wide/fluid、旧地址重定向；编辑器/diff 路由懒加载随 F2 接入。
- [x] Dialog/Drawer/Tabs/PageState/Toast 公共组件。
- [x] `lib/events.ts` 唯一 SSE 实现；`lib/screen-identity.ts` 唯一屏幕身份实现（旧 `twin` 文件改为薄包装/复用，F6 删除）。
- [x] jsdom + Testing Library；mock 入口已建立，类型绑定等 B1.5 生成后接入。

**门禁**：四类身份导航正确；无手写 DTO；`typecheck/test/build` 通过。

### F1：组织与 Agent 接入

> **F1–F4 状态校正（2026-11-25）**：下文 `[ ]` 表示已有部分实现、但尚未满足冻结需求，不代表未开始。完整差异见 [frontend-gap-audit.md](./frontend-gap-audit.md)。本批已修复工作流节点选择/已发布只读/派生跳转、任务新建/结果提交/审批处理、消息 `message.created` SSE 与 Agent token 全局传递等 P0 问题；这不代表 F1–F4 已全量完成。

- [ ] 员工/岗位/角色/团队；员工抽屉四页签。基础页面已建；真人/Agent 子 Tab、完整档案、联系人、技能编辑、岗位/角色绑定与工位拖拽等未齐。
- [ ] 邀请（默认员工、`data_scope=self`）、撤销/重发、410。基础创建能力已有；登录名、权限模板、复制链接及撤销/重发入口未齐，真人邀请列表仍受契约缺口阻塞。
- [ ] 21 权限编辑器与模板，仅展示可授权子集。基础勾选已有；模板、`data_scope`、授权上界过滤与非超管只读视图未齐。
- [ ] Agent 外壳、endpoint 审批、token 轮转与软注销。基础操作已有，token 明文已改为组件状态传递；详情抽屉、审批地址对比/校验结果、健康检查、待办与心跳信息等未齐。
- [ ] 邀请码三页签（HTTP curl / MCP 四工具配置 / system_prompt 接入说明）。展示已有；岗位、业务角色/模板、期限、详情、权限边界与示例正确性未齐。

### F2：工作流

- [ ] 卡片列表、四模板、版本、发布校验定位、409、软删除。基础卡片与版本操作已有；四模板、版本页、发布前校验/二次确认/错误定位、搜索与完整卡片字段未齐。
- [ ] `@xyflow/react` 编辑器：六类节点、连线规则、条件/并行/打回、扇出互斥、显式 join、终验零/一回边。画布与节点增删已有；连线规则与扇出配置等未实现。
- [ ] 属性表单。基础字段与已有节点点击编辑已修；岗位选项、条件构建、变量提示等未齐。
- [ ] `{graph,revision}` 保存与版本约束。CAS/409/force 已有，已发布只读与派生跳转已修；发布前校验/二次确认、校验定位与 dirty 离开拦截未齐。
- [ ] 条件构建器（当前 condition 字段仅支持纯字符串标签）、JSON 同步、变量提示、双版本 diff（待后端补齐或后续迭代）。

### F3：任务中心

- [ ] 三 Tab（全部 / 我的工作 / 审批）、筛选、角标、状态标签、四类终止原因。审批 Tab 已接真实审批列表；我的工作分组、状态多选、关键词/时间筛选与角标口径未齐。
- [ ] 详情时间线、当前 run 卡、概览、节点 Run 列表。基础信息已有；需求要求的节点切换布局、结果摘要/产物数及 SSE 局部刷新未齐。
- [ ] 认领 409；结果提交、`attempt_no`、stale 409；终验通过/驳回、或签提示、升级处理。本批已补结果对话框、归属/运行状态门控及审批处理；产物上传受契约缺口阻塞，升级处理等仍需对照验收。
- [ ] 扇出 `fanout_group + fanout_slot`；join missing 与 `rerun-join` 确认范围。基础展示与二次确认已有；前驱终态/missing 分片及权限口径未齐。
- [ ] 取消 `cancelTask` + `CancelIn.reason` 默认 manual；软删除活跃 run 返回 409。接口与 409 处理已有；发起人/超管可见性仍待修正。
- [ ] 变量、产物（`TaskDetailOut` 契约未暴露 `task_context` / `run_context` / artifacts 列表，已做占位降级提示，待后端扩展）。

### F4：消息、追迹、概览、指标

- [ ] 消息筛选/详情/发送/SSE 实时刷新。本批已接 `message.created` 并显示连接状态；任务追迹 Tab、新消息 2 秒高亮、完整筛选与详情字段未齐。
- [ ] 追迹/审计列表 + 筛选 + 详情抽屉。基础列表已有；告警、通知规则、字段级 diff、结果/IP 列及导出未齐。
- [x] 概览快照（`OverviewOut` 生成类型，移除手写 DTO）。功能项保留；组件直连 `api()` 与 health 手写类型的横切问题见审计。
- [ ] 指标：概览卡、自画 SVG 趋势、排行进度条、7d/30d/自定义、CSV 导出。展示原语已有；趋势/排行指标口径、八项卡片与加载空态仍需按需求补齐并联调。

### F5：协同大屏与孪生

- [x] `/console/collab`：屏幕列表（来源/在线/最后心跳）、三布局、可视化编辑、草稿/发布、预览、全屏、聚焦、删除。
- [x] `/twin`：匿名 kiosk、登录交互模式、5 分钟退回、auto 主题、reduced-motion。公开投影只消费白名单，不渲染 team/endpoint/token/creator。
- [ ] 后端 POST/GET screens 补齐后把 upsert/get 的 fallback 改直连（已标记，不阻塞 F5 交付）。
- [ ] 审计、告警、集成、技能包、设置向导（已存在占位页，后续迭代增强）。

### F6：切换与清理

- [ ] 逐域关闭 mock，按生成类型联调（需后端全部启动后逐项关 mock 做 smoke，前端侧无阻塞）。
- [x] 删除旧 Staff/Teams/Approvals 页面、旧导航、旧权限分支、`twin/stream.ts` 重复实现。
- [ ] 全量浏览器验收 + `typecheck/test/build`（`typecheck/test/build` 通过；浏览器验收尚未做，且 F5 对照需求 §6.1 差距很大，需重做后再验收）。

---

## 6. 删除清单（F6 必须逐项打勾）

- [x] 旧 `/console/staff`、`/console/teams`、`/console/approvals` 页面组件（ConsoleStaffPage 重写保留 join 路由，旧 Teams/Approvals 整文件删除）
- [x] 旧平铺导航与旧 `capabilities` 判断分支（已在 F0 完成分组导航 + RequirePermission）
- [x] `twin/stream.ts` 第二套 SSE（re-export + `@deprecated F6 后删除`）
- [x] 两处屏幕登记/存储逻辑合并后的残留（sessionStorage 无残留，统一 useScreenSession）
- [x] 手写 DTO/重复 interface（ConsoleStaffPage 旧 DTO 全部删除）
- [x] 无引用旧 `DataTable`、旧 `WriteFailToast`（DataTable + datatable.test.tsx 删除，WriteFailToast F0 已删）

---

## 7. 门禁与命令

```powershell
cd e:\ai_tools\mailbus\web
npm run gen:types
npm run typecheck
npm test
npm run build
```

- CI 额外执行 `npm run gen:types` 后 `git diff --exit-code`，防止契约漂移。
- 每阶段用 1024/1280 真实浏览器验收。
- F5 额外验证：重启后屏幕身份复用、无 Header 心跳 403、`preview=1` 不登记、公开投影无 team、403/404/409/429/503。

---

## 8. 交付物

- [ ] `lib/contracts.ts`（生成）与生成脚本
- [ ] 每域 `api.ts` / `hooks.ts` / `view.ts` / `schema.ts`
- [ ] `lib/screen-identity.ts`、`lib/events.ts` 单一实现
- [ ] 13 个控制台页面 + `/twin`
- [ ] 工作流编辑器、大屏配置与可视化布局
- [ ] 删除清单全部完成后的干净构建
