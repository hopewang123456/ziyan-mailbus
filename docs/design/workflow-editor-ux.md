# 工作流拖拽编辑器 · 交互稿

> 2026-11-24 · v1.1（最终跨端契约已冻结）
> 配套：[agent-unification-design.md](./agent-unification-design.md) 第 3.1 节 `wf_nodes` / `wf_node_transitions`、第 4 章工作流引擎、11.4 编辑器
> 目标：把已确认的 8 项编辑器决策落成可实施规格，前端与后端可各自开工，且对同一批字段、状态、错误码有一致理解。

---

## 0. 已定决策（本稿的前提）

| # | 议题 | 结论 |
|---|---|---|
| E1 | 形态 | **独立整页编辑器**，不是弹窗、不是侧滑。路由 `/console/workflows/:workflowId/versions/:version/editor` |
| E2 | 画布库 | `@xyflow/react`（需新增前端依赖），不使用自研画布 |
| E3 | 坐标存储 | `wf_nodes.pos_x` / `pos_y`，画布逻辑坐标（px），与缩放无关 |
| E4 | 保存 | **显式保存**（Ctrl+S / 顶栏按钮），不自动保存；有未保存修改时离开页面需确认 |
| E5 | 条件规则 | 可视化构建器（AND/OR 嵌套 + field/op/value）与 JSON 源码**双模式**，双向同步 |
| E6 | 扇出 | 节点属性里的**开关 + 并发员工数 N**，运行时按候选池自动取人；不额外画线。**扇出节点只允许 1 条出边，与多出边/条件分支互斥（已确认）** |
| E7 | 版本对比 | 本期做**只读 diff**（节点/连线/字段差异高亮），不做合并 |
| E8 | prompt 模板 | 纯文本 + 变量插入按钮（`task.*` / `node.*` / `result.*` / `artifacts`）+ 右侧实时渲染预览 |
| E9 | 最终结构与保存 | 多个前向入边只能进入显式 `parallel_join`；终验仅零或一条回边；Graph 乐观锁使用整数 `revision`，`force=true` 覆盖保存并审计 |

补充约束：

- 编辑器与 `wf_nodes` / `wf_node_transitions` **一一对应**，不引入额外存储格式；节点表新增字段仅 `pos_x` / `pos_y`，版本表另增整数 `revision` 用于乐观锁。
- 视觉沿用 ConsoleKit 暗色 token：`abyss`（底）、`hull`（面板）、`rail`（描边）、`mute`（次级文字）、`frost`（主文字）、`mint`（成功）、`amber-signal`（警示）、`flare`（错误）。字体 `font-display` 标题、`font-mono` 标识符。
- 不新增 UI 框架、不新增状态管理库；画布状态用 React state + reducer，undo/redo 为内存栈（最多 50 步）。
- 新增前端依赖：`@xyflow/react`（画布）、`@uiw/react-codemirror` + `@codemirror/lang-json`（JSON 条件编辑）；不加主题包、不加 dagre。

---

## 1. 入口与信息架构

### 1.1 入口

| 入口 | 行为 |
|---|---|
| 工作流模板页（`ConsoleWorkflowsPage`）版本表 | 草稿行出现「编辑」按钮；已发布行出现「查看」+「派生草稿」 |
| 版本节点列表 | 从原来的 `1.节点A → 2.节点B` 文本列改为只显示节点数，点击行进入编辑器 |
| 新建草稿后 | 成功后直接跳转编辑器（替换现有"新增草稿版本"文本域流程，文本域保留为降级入口，Phase 5 后移除） |
| 复制链接 | 支持直接粘贴 URL 进入，带登录门槛 |

权限：

- 进入编辑器：`workflow_modify`（可编辑）或 `workflow_publish`（可编辑）或仅有查看权限（只读模式）。
- 保存：`workflow_modify`。
- 发布：`workflow_publish`（C2 新增权限）。
- 派生草稿：`workflow_modify`。

### 1.2 路由

```
/console/workflows/:workflowId/versions/:version/editor      编辑 / 只读
/console/workflows/:workflowId/versions/:version/diff/:other 版本对比（只读）
```

`version` 为整数。编辑器挂在 `ConsoleApp` 内部（共用登录态与导航），但需要**全宽铺满**：给 `ConsoleLayout` 增加 `fluid` 模式，命中编辑器/对比路由时 `main` 改为 `max-w-none p-0 h-screen overflow-hidden`。不改动其他页面的 `max-w-5xl px-6 py-6` 布局。

### 1.3 页面状态机

```
loading ──ok──> ready(draft, clean) ──编辑──> ready(draft, dirty)
                    │                              │
                    │                              ├─保存──> clean
                    │                              └─校验──> clean（校验不改 dirty）
                    ├──只读（published 或无权限）──> readonly
                    └──加载失败──> error（重试 / 返回列表）
```

- `draft` 且 `state=published` 不可能同时存在：版本发布后即为只读。
- 已发布版本要改 → 「派生草稿」：复制当前图为新版本号（`latest_version + 1`，`state=draft`），跳转新版本编辑器，原版本保持只读；若已有草稿先提示（见 10.5）。

---

## 2. 页面布局

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ ← 返回   合同评审 v3  [草稿]  ● 未保存                    最后保存 14:02            │
│                                          [校验 2]  [版本对比]  [保存]  [发布] [⋯]   │
├──────────────┬─────────────────────────────────────────────────┬─────────────────┤
│ 节点库        │                                                 │ 属性 / 校验      │
│              │                                                 │                 │
│ ◆ 开始        │              ┌─────────┐                        │ 节点 · 市场研究  │
│ ▭ Agent 执行  │              │  开始   │                        │ ─────────────── │
│ ▭ 真人任务    │              └────┬────┘                        │ 名称  [市场研究] │
│ ◇ 条件分支    │                   │                             │ 节点类型 Agent   │
│ ⬡ 并行汇聚    │              ┌────▼─────┐      ┌──────────┐     │ 岗位  [产品经理▾]│
│ ▭ 最终审批    │              │ 市场研究 │─────▶│ 竞品复核 │     │ 超时  [72h]      │
│              │              └────┬─────┘      └────┬─────┘     │ 重试  [3]        │
│ ─────────    │                   │ 条件            │            │ 循环上限 [3]     │
│ 图概览        │              ┌────▼─────┐      ┌────▼─────┐     │ 扇出  [关]       │
│ 节点 8        │              │ 法务审查 │      │ 终验审批 │     │ ─────────────── │
│ 连线 9        │              └──────────┘      └──────────┘     │ 指令模板         │
│ 深度 5        │                                                 │ [textarea]      │
│              │  [－][100%][＋] [适应画布] [自动布局]   [小地图]   │ 预览             │
├──────────────┴─────────────────────────────────────────────────┴─────────────────┤
│ 校验结果（2 错误 / 1 警告）                                                    ▲ │
│ ✕ E_NO_POSITION  节点「法务审查」未绑定岗位      [定位]                          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

尺寸：

- 顶栏 48px 固定。
- 左面板 208px，可折叠为 40px 图标条。
- 右面板 320px，可折叠；无选中时显示「版本概览 + 校验摘要」。
- 底部校验抽屉 0 / 176px 两档，默认收起；有 error 时不自动弹开，只在顶栏显示红色计数徽标。
- 画布占满剩余空间；窗口最小支持 1280px，窄于 1440px 时右面板默认收起。

---

## 3. 画布

### 3.1 基础交互

| 操作 | 行为 |
|---|---|
| 拖拽空白处 | 框选（默认），`Space` 或中键按下为平移 |
| 滚轮 | 垂直滚动；`Ctrl/⌘ + 滚轮` 缩放 |
| 双击空白 | 弹出快捷新增菜单（6 类节点，按双击位置落点） |
| 双击节点标题 | 就地重命名，Enter 确认 / Esc 取消 |
| 右键节点 | 上下文菜单：重命名 / 复制 / 删除 / 从此节点新建连线 |
| 右键画布 | 粘贴 / 适应画布 / 自动布局 |
| 首次加载 | `fitView`（padding 0.2，最大 zoom 1），动画 200ms |

底部工具条（左）：`－` / 缩放百分比（点击重置 100%）/ `＋` / 适应画布 / 自动布局。
右下：MiniMap（节点按类型着色，视口矩形可拖拽）。
背景：点阵网格，`gap 16`，缩放自适应。

### 3.2 自动布局

不引入 dagre。用 BFS 最长路径分层：从 start 出发，`layer(v) = max(layer(u)+1)`；回边不参与分层。横向间距 260px，纵向 140px，按层内顺序排列。点击后 300ms 位移动画，结果写入 `pos_x/pos_y` 并标记 dirty，可 Ctrl+Z 撤销。

### 3.3 坐标读写

- 读取：`pos_x/pos_y` 直接作为 `position`；若为 `null` 或缺失（旧数据迁移后），按 `seq` 线性排布（x = seq * 260，y = 0）并标记 dirty。
- 写入：节点拖拽结束时四舍五入到整数 px 存入草稿状态，保存时随 graph 一起 PUT。
- 缩放、平移**不改变**坐标。

---

## 4. 节点

### 4.1 六类节点的视觉

| node_type | 形状 | 颜色 | 角标 | 尺寸 |
|---|---|---|---|---|
| `start` | 胶囊（圆角 999） | mint 描边 + 8% 填充 | 「开始」 | 140×48 |
| `agent` | 圆角矩形 r=8 | rail 描边 + hull 填充 | 岗位名 | 200×80 |
| `human` | 圆角矩形 r=8，虚线描边 | amber-signal | 「真人」 | 200×80 |
| `condition` | 菱形（旋转 45° 的矩形） | frost 描边 | 「条件」 | 160×80（视觉 113×113） |
| `parallel_join` | 圆角矩形 r=8，双线描边 | mint | 「汇聚」 | 180×72 |
| `final_approval` | 圆角矩形 r=8，2px 描边 | flare | 「终验」 | 200×80 |

节点卡内部结构（agent / human / final_approval）：

```
┌────────────────────────────┐
│ 市场研究            [产品] │  ← 标题 13px frost；岗位 chip 10px
│ 竞品分析 · 2 条前序产物     │  ← 副标题 11px mute，超长省略
└────────────────────────────┘
```

- 选中：`ring-2 ring-frost`，四角锚点全部显示。
- 校验错误：`border-flare` + 右上角红色 `!` 圆点；警告：amber 圆点。
- 悬停：显示四个连接锚点（上下左右），`cursor: crosshair`。
- 扇出开启：标题右侧加 `×N` mono 角标。
- 节点多于 300 个时关闭阴影、缩小副标题（性能降级，本期仅告知实现方）。

### 4.2 新增节点

1. 左面板拖拽到画布 → 松手位置即节点中心，自动选中、右面板打开、名称进入编辑态并全选。
2. 双击画布 → 快捷菜单，点选类型后在双击点创建。
3. 从已有节点锚点拖出到空白处松手 → 弹出快捷菜单，创建的节点自动与源节点连线。

默认字段：`name` = 类型中文名（可重复，仅提示），`node_id` 前端生成 `node_<slug>_<4位随机>`，`seq` = 当前最大 seq + 1，`max_retries/max_loops = 3`，`needs_artifacts_from = []`，`config = {}`，坐标取落点。

- `start` 全图唯一；已存在时节点库中的「开始」置灰并提示「已有开始节点」。
- `condition` / `parallel_join` 无岗位、无 prompt，仅作为结构节点。

### 4.3 节点类型切换

右面板「节点类型」下拉允许切换，切换时二次确认：

> 切换类型会清空不适用的字段（如岗位、指令模板、扇出设置），是否继续？

切换后保留：`name`、`node_id`、坐标、入出边（`start` 除外，见 5.4）。

### 4.4 删除节点

Delete / Backspace 或右面板「删除节点」：连同其所有入边、出边一起删除；不弹确认（可撤销），若该节点是 `start` 则需确认「删除开始节点后工作流将无法发布」。

---

## 5. 连线（`wf_node_transitions`）

### 5.1 连线语义

| 类型 | 判定 | 样式 | 图例文字 |
|---|---|---|---|
| 普通边 | 有 `condition` 为空，且源节点出边只有 1 条 | 实线 mute，箭头 | 无 |
| 条件边 | `condition` 非空 | 实线 frost + 条件摘要 chip | `score ≥ 0.8` |
| 并行边 | 源节点 ≥2 条出边且全部 `condition` 为空 | 实线 mute，标签「并行」 | 并行 |
| 打回边 | 目标节点是源节点的祖先（构成环） | 虚线 flare，标签「打回」 | 打回 |

- 「打回」不是独立字段，由**拓扑关系推断**（成环即为回边），与引擎 4.5 的"走回边再次进入"一致，不新增 DB 列。
- 条件边摘要：由规则生成人类可读文本，超过 24 字符截断，hover 显示完整规则 JSON 摘要。

### 5.2 创建连线

1. 悬停源节点 → 拖出锚点 → 落到目标节点主体 → 创建。
2. 落到空白 → 快捷新增菜单（4.2 第 3 条）。
3. 创建时即时校验，不合法则红线回弹 + toast：

| 规则 | 结果 |
|---|---|
| 自环 `from == to` | 拒绝：`E_SELF_LOOP` |
| 重复边（同 from/to） | 拒绝：「连线已存在」 |
| 连入 `start` | 拒绝：「开始节点不能有入边」 |
| `final_approval` 的出边不成环 | 拒绝：「终验节点的出边只能是打回（指向前序节点）」 |
| `final_approval` 已有 1 条回边仍新增出边 | 拒绝：`E_FINAL_REWORK_EDGES`，终验只允许零或一条回边 |
| 普通节点将具有第 2 条前向入边 | 拒绝：`E_MULTI_IN_REQUIRES_JOIN`，提示先插入 `parallel_join`；回边不计入 |
| 源节点已有扇出且新增第 2 条出边 | 拒绝：「扇出节点只能有一条出边」 |

### 5.3 选中与编辑连线

点击连线 → 选中（加粗 mint），右面板切到「连线」页：

```
连线 · 市场研究 → 竞品复核
────────────────────────
类型      条件边（不可手改，由规则决定）
条件      [可视化] [JSON]
          ┌ 全部满足 (AND) ─────────────┐
          │ field [result.score ▾] op [≥▾] value [0.8]  ✕ │
          │ [+ 条件]  [+ 分组]                            │
          └──────────────────────────────────────────────┘
[删除连线]
```

- 条件为空 → 类型显示「普通边」；成环 → 顶部加 `打回` 红色提示，并提示「目标节点循环上限 max_loops=3」。
- 删除连线：Delete 键或面板按钮。

### 5.4 多出边的组合规则（对齐引擎语义）

- 出边 1 条：普通/回边，无歧义。
- 出边 ≥2 条：**必须全部带条件**（条件分支）**或全部不带条件**（并行分支）。
- 混合（部分带条件）→ `E_MIXED_OUT_EDGES`，连线处红色，校验抽屉给修复建议「给其余出边补条件，或删除多余出边」。
- 全部带条件时**不设隐式默认分支**：运行期若所有条件均未命中，**任务自动终止**（`cancelled`，`termination_reason = no_matching_branch`，设计文档 4.6），因此建议条件互斥且覆盖完整。
- 扇出与多出边**不可同时使用**（同节点同时开启 fanout 且有 ≥2 条出边 → `E_FANOUT_WITH_MULTI_OUT`）。扇出是"同节点多人做同一件事"，多出边是"不同节点做不同事"，语义不同，禁止混用避免引擎歧义。

### 5.5 多入边与终验回边

- 统计入边时先按拓扑区分前向边与回边；回边不参与“多入边必须汇聚”的计数
- 普通节点前向入边最多 1 条；新增第 2 条立即提示 `E_MULTI_IN_REQUIRES_JOIN`，发布时后端再次强制校验
- 多条前向边必须先汇入 `parallel_join`，再由 join 的唯一后续路径向下游推进；join 等全部前驱当前 run 进入 done/failed/skipped 后统一汇总，failed/skipped 显示为 missing
- missing 分片人工补完后不自动重跑 join；任务详情由发起人或超管显式触发，产生新 join attempt 与下游 run，并展示本次重跑范围
- `final_approval` 零回边：驳回后任务 `cancelled`，`termination_reason=approval_rejected`；一条回边：驳回进入重做；多条回边：发布报 `E_FINAL_REWORK_EDGES`

---

## 6. 属性面板（右）

无选中 → 版本概览：

```
版本概览
v3 · 草稿 · 未保存
节点 8 · 连线 9 · 最大深度 5
创建 2026-11-24 13:40 · 更新 14:02
[校验] [导出 JSON]
```

选中节点 → 分区折叠（记住展开状态）：

### 6.1 字段与可见性

| 字段 | 控件 | start | agent | human | condition | parallel_join | final_approval |
|---|---|---|---|---|---|---|---|
| 名称 `name` | 输入 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 节点类型 `node_type` | 下拉 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 岗位 `position_id` | 岗位下拉（`GET /api/options/positions`） | — | ✓ | ✓ | — | — | ✓ |
| 指定员工（覆盖） | 员工下拉（按岗位过滤，`GET /api/options/employees?position_id=`），写 `config.assignee_id` | — | ✓ | ✓ | — | — | ✓ |
| 指令模板 `prompt_template` | 文本域 + 变量按钮 + 预览（第 8 节） | — | ✓ | ✓ | — | ✓ | ✓ |
| 前序产物 `needs_artifacts_from` | 多选（仅列出拓扑前序节点） | — | ✓ | ✓ | — | ✓ | ✓ |
| 最大重试 `max_retries` | 数字 0–10，默认 3 | — | ✓ | — | — | — | — |
| 循环上限 `max_loops` | 数字 0–10，默认 3；有入向回边时高亮 | — | ✓ | ✓ | — | — | ✓ |
| 超时 `timeout_seconds` | 时长输入，留空 = 类型默认 | — | ✓ | ✓ | — | — | ✓ |
| 扇出 | 开关 + 人数 N（2–10），写 `config.fanout` | — | ✓ | — | — | — | — |
| 工位覆盖 `config.seat_id` | 工位下拉（`GET /api/teams/{id}/seats`），留空 = 自动 | — | ✓ | ✓ | — | — | ✓ |
| 触发方式（`config.trigger`） | 多选：手动 / 消息 / 定时（+ cron 输入） | ✓ | — | — | — | — | — |
| 删除节点 | 按钮（危险） | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

- 类型默认超时：`final_approval` 24h（86400），其余 72h（259200），输入框 placeholder 显示默认值。
- 扇出开关的双向互斥拦截：
  - 先有多条出边再开扇出：开关置灰，提示「该节点有多条出边，需先删除多余连线，或改用并行汇聚节点」。
  - 先开扇出再加第 2 条出边：连线被拒绝（5.2），提示「扇出节点只能有一条出边」。
  - 两者都通过校验兜底，报 `E_FANOUT_WITH_MULTI_OUT`。
- 定时触发：cron 为标准 5 段，时区固定 Asia/Shanghai；错过的触发在服务端 1 小时内补跑一次；同一工作流同时只允许一个运行实例（详见设计文档 4.10）。启用定时但 cron 为空或非法时校验报 `E_TRIGGER_CRON`。
- 消息触发：仅响应 `kind=command` 且携带 `workflow_id` 的指令消息，发送者须为已注册员工；普通聊天与广播不触发（详见设计文档 4.10）。
- 岗位为空时，该字段下方出现 amber 提示「未绑定岗位，运行时会停留等待指派」，并在画布节点上加 amber 圆点。
- `condition` 节点属性页不展示字段，改为提示 + 出边列表：

```
条件分支
条件配置在出边上，每个出口一条规则。
出边（2）
 → 通过 · score ≥ 0.8      [编辑]
 → 退回 · score < 0.8      [编辑]
[+ 添加出口]
```

- `parallel_join` 属性页展示前向入边数量与「等全部前驱 run 进入终态后统一汇总；missing 分片补完后需在任务详情显式重跑 join」说明。
- `start` 属性页额外展示「开始节点唯一，无入边」。

### 6.2 表单行为

- 输入即时写入本地草稿（不请求后端），标记 dirty。
- 数字类字段失焦时纠正到合法范围并提示一次。
- 名称失焦去重提示（同名仅警告，不改 node_id）。
- 字段变更立即反映到画布（标题、岗位 chip、`×N` 角标、告警点）。

---

## 7. 条件规则：构建器与 JSON 双模式

### 7.1 数据结构（与设计文档 4.6 完全一致）

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

单条规则可省略 `and` 包裹，直接 `{"field": "...", "op": "...", "value": ...}`。

### 7.2 可视化构建器

```
┌ 全部满足 (AND) ▼ ─────────────────────────────┐
│  [result.score ▾] [≥ ▾] [0.8]        ✕        │
│  ┌ 任一满足 (OR) ▼ ──────────────────────┐    │
│  │ [result.status ▾] [= ▾] [approved] ✕ │    │
│  │ [artifacts.node_req.file_type ▾]      │    │
│  │   [属于 ▾] [md] [pdf] ✕               │    │
│  └───────────────────────────────────────┘ ✕  │
│  [+ 条件]  [+ 分组]                            │
└───────────────────────────────────────────────┘
```

- 顶层默认 `and`（「全部满足」），可切 `or`（「任一满足」）。分组同样可切。
- 每行：field 可输入可选的 combobox；op 下拉；value 随 op 变形：
  - `in` / `not_in` → 标签输入（Enter 添加，退格删除）
  - `contains` / `startsWith` / `endsWith` / `regex` → 单行文本
  - 其余 → 单行文本，数字自动转 number
- field 建议值分组展示：
  - `result.*`：常见 `score` / `status` / `decision` / `summary`
  - `task.*`：`task_id` / `title` / `owner_id`
  - `node.*`：当前节点的 `name` / `node_id` / `attempt_no`
  - `context.*`：任务入参变量
  - `artifacts.<node_id>.*`：前序节点产物元数据（`file_type` / `file_name` / `producer` / `path`）
- 允许自由输入路径，实时校验语法 `^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$`，前缀必须在白名单内，否则行内红字 `E_CONDITION_FIELD`。
- 分组可嵌套最多 3 层；超过提示「层级过深，建议改用 JSON」。
- 删除最后一个条件时保持空分组，父级提供「删除分组」。

### 7.3 JSON 模式

- 编辑器：CodeMirror 6（`@uiw/react-codemirror` + `@codemirror/lang-json`），懒加载，仅在切到 JSON 页签时挂载。
- 能力：JSON 语法高亮、行号、括号匹配与自动闭合、代码折叠、当前行高亮；`jsonParseLinter` 提供行内语法诊断（红色波浪线 + 行号槽标记）。
- 主题：不引入第三方主题包，用 `EditorView.theme({...}, {dark: true})` 按现有 token 定制——背景 `hull`、文字 `frost`、行号与提示 `mute`、选中 `rail`、错误 `flare`、字符串/数字/关键字分别用 `mint` / `amber-signal` / `frost`。
- 尺寸：高 280px（最小 220 / 最大 360），内容超出滚动；只允许垂直滚动，不出现横向滚动条（超长行软换行）。
- 切换到 JSON 时：把当前可视化树 `JSON.stringify(rule, null, 2)` 填入。
- JSON → 可视化：解析成功且结构合法才切换；失败则停留 JSON，顶部提示「JSON 有 N 处语法错误」，首处错误自动滚入视野，并提供「保留 JSON 并继续编辑」。
- 两种模式共享同一份草稿值；切换不丢改动。
- 空条件：JSON 展示空对象 `{}` 并提示「空规则 = 无条件前进」；保存时 `condition` 写 `null`。
- 快捷键边界：
  - 编辑器内 `Ctrl/⌘ + Z` 只撤销 JSON 文本（CodeMirror 自身 history），不影响画布 undo 栈；画布 undo 仅在焦点不在编辑器时生效。
  - `Ctrl/⌘ + S` 在编辑器内仍触发页面保存（在 CodeMirror keymap 中拦截并调用保存，不让浏览器默认行为吞掉）。
  - `Ctrl/⌘ + Enter` 校验并尝试切回可视化模式，失败则停留。
  - `Tab` 在编辑器内缩进（不跳出焦点），`Esc` 先退出编辑器焦点再取消选中。

### 7.4 规则校验（前端即时 + 后端权威）

| 代码 | 触发 |
|---|---|
| `E_CONDITION_SYNTAX` | JSON 解析失败或结构不符合 `{and|or:[...]}` / 单规则 |
| `E_CONDITION_FIELD` | field 前缀不在白名单或路径语法错误 |
| `E_CONDITION_OP` | op 不在白名单 |
| `E_CONDITION_VALUE` | `in/not_in` 值非数组、`regex` 非法正则、数值 op 配非数字 |
| `E_CONDITION_EMPTY_GROUP` | 分组内无子条件 |

---

## 8. prompt 模板与预览

### 8.1 编辑区

```
指令模板
┌────────────────────────────────────────────┐
│ 你是{{role.role_name}}，负责{{node.name}}。 │
│ 请基于以下产物完成工作：                    │
│ {{artifacts}}                              │
│ 完成标准：{{task.title}}                    │
└────────────────────────────────────────────┘
[＋ 变量]  [全屏]
```

- 「＋ 变量」弹出分组菜单：
  - `task.*`：`task_id` / `title` / `owner_id` / `created_by`
  - `workflow.*`：`workflow_id` / `version`
  - `node.*`：`node_id` / `name` / `attempt_no`
  - `role.*`：`role_name` / `capabilities`
  - `previous.result`：上一节点结果
  - `artifacts`：产物清单（渲染为路径/文件名/描述/产出人列表）
- 插入在光标处，插入后可选中的变量 token 用 `font-mono text-mint` 高亮（用 overlay 渲染，底层仍是纯文本）。
- 全屏：覆盖画布区域的模态编辑，Esc 退出。

### 8.2 实时预览

右侧（或下方折叠）「预览」用当前节点的**样例数据**渲染：

- 样例来自：`node.name` 用真实值；`task.*` 用「示例任务」；`role.*` 用岗位绑定的第一个角色；`previous.result` 与 `artifacts` 用占位文案。
- 未识别变量渲染为 `{{var}}` 并标红，附提示「变量不存在」。
- 预览只做字符串替换，不求值条件、不请求后端。
- 预览区高度 160px，可折叠；文本超长滚动。

### 8.3 变量校验

- `E_PROMPT_UNKNOWN_VAR`：警告级（不阻断保存，不阻断发布）。
- 变量白名单与后端 4.8 保持一致，前端维护同一份常量（建议放 `web/src/lib/workflow/promptVars.ts`，后端在导出契约里提供同一列表）。

---

## 9. 校验

### 9.1 触发

- 顶栏「校验」按钮（手动）。
- 保存前自动跑一次前端校验，有结构性错误（见 9.4）则阻断保存。
- 发布前调用后端 `POST .../validate`，必须零 error。
- 编辑过程中前端做**轻量即时校验**（每次图变更 300ms 防抖），只更新节点/连线上的红黄点与顶栏计数，不弹面板。

### 9.2 错误与警告清单

| 代码 | 级别 | 说明 | 定位 |
|---|---|---|---|
| `E_MISSING_START` | error | 缺少开始节点 | 版本概览 |
| `E_MULTI_START` | error | 开始节点多于 1 个 | 各 start 节点 |
| `E_NO_FINAL` | error | 没有终验节点 | 版本概览 |
| `E_NO_POSITION` | error | agent/human/final_approval 未绑岗位（且未指定员工） | 节点 |
| `E_ORPHAN_NODE` | error | 不可从 start 到达的节点 | 节点 |
| `E_CYCLE_UNCONDITIONAL` | error | 环上没有任何条件边，且目标节点 `max_loops = 0` | 环上各边 |
| `E_SELF_LOOP` | error | 自环 | 边 |
| `E_FINAL_FORWARD` | error | 终验节点存在不成环的出边 | 边 |
| `E_START_INBOUND` | error | 开始节点有入边 | 边 |
| `E_MIXED_OUT_EDGES` | error | 多出边中部分带条件、部分不带 | 源节点 + 各出边 |
| `E_FANOUT_WITH_MULTI_OUT` | error | 同时开扇出与多出边 | 节点 |
| `E_FANOUT_INVALID` | error | 扇出人数 < 2 或 > 10 | 节点 |
| `E_MULTI_IN_REQUIRES_JOIN` | error | 普通节点有超过 1 条前向入边；回边不计入 | 目标节点 + 入边 |
| `E_FINAL_REWORK_EDGES` | error | 终验节点有超过 1 条回边 | 终验节点 + 回边 |
| `E_CONDITION_*` | error | 见 7.4 | 边 |
| `E_DUPLICATE_NODE_ID` | error | node_id 重复 | 节点 |
| `E_INVALID_NODE_ID` | error | node_id 不符合 `^[a-z][a-z0-9_]{0,63}$` | 节点 |
| `E_TRIGGER_CRON` | error | start 节点启用定时但 cron 为空或非法 | 节点 |
| `W_NO_PROMPT` | warning | agent 节点无指令模板 | 节点 |
| `W_HUMAN_NO_PROMPT` | warning | human 节点无任务说明 | 节点 |
| `W_PROMPT_UNKNOWN_VAR` | warning | 模板变量未知 | 节点 |
| `W_HIGH_FANOUT` | warning | 扇出人数 > 5 | 节点 |
| `W_LONG_TIMEOUT` | warning | 超时 > 7 天 | 节点 |

### 9.3 展示

- 顶栏：`校验 2` 红色 / `校验 0` mint。
- 底部抽屉：分组「错误」「警告」，每行 `代码 chip + 描述 + [定位]`。
- 点「定位」：选中并居中该节点/边（zoom 1，padding 0.3），节点脉冲高亮 600ms，右面板切到对应属性。
- 只读模式隐藏校验按钮（发布时已经校验过）。

### 9.4 结构性错误（阻断保存）

仅 4 类：`E_DUPLICATE_NODE_ID` / `E_INVALID_NODE_ID`、悬空边（`from/to` 不存在）、节点 ID 非法、条件 JSON 无法解析。其余语义错误允许保存（草稿阶段允许半成品）。

---

## 10. 保存、发布、离开

### 10.1 保存

- 顶栏「保存」按钮 + Ctrl/⌘+S。
- dirty 时按钮可用并显示 `● 未保存`；保存中按钮 loading，禁用重复点击。
- 请求：`PUT /api/workflows/{workflow_id}/versions/{version}/graph`，body 为 `{graph, revision}`；`revision` 是打开/上次保存时取得的整数。
- 成功：服务端 revision +1；本地更新 `revision` 与 ISO UTC `updated_at`，清 dirty，toast「已保存 14:02」。
- 失败：
  - 400（结构性）：抽屉展开并定位错误，不退出编辑。
  - 403：toast「无保存权限」，按钮转只读。
  - 409：弹窗「该版本已被他人修改（当前 revision {server_revision}，最近保存 14:01）」，提供「重新加载（丢弃本地改动）」/「覆盖保存」/「取消」。覆盖保存仍带原 body `{graph,revision}` 并加 `?force=true`，服务端记录基准 revision 与覆盖审计。
  - 网络错误：保留 dirty，toast 可重试。

### 10.2 发布

1. 点击「发布」→ 前端先跑本地校验，再调后端 validate。
2. 有 error：抽屉展开，toast「存在 2 个错误，无法发布」。
3. 有 warning 无 error：确认弹窗列出警告摘要。
4. 确认弹窗文案：

```
发布 v3？
发布后版本不可编辑；新任务将使用 v3，运行中的任务仍锁定原版本。
节点 8 · 连线 9
[取消] [确认发布]
```

5. 成功：页面切只读态，顶栏 badge 变「已发布 · v3」，toast「已发布 v3」；「发布」按钮变为「派生草稿」。

### 10.3 离开提醒

- dirty 时拦截所有离开动作（侧边导航、返回、浏览器关闭/刷新）。
- 应用内跳转：弹窗「有未保存的修改」，选项「保存并离开」/「放弃修改」/「继续编辑」。
- 浏览器关闭：`beforeunload` 原生提示（不自定义文案）。
- 实现：`react-router-dom` v7 的 `useBlocker` + `useBeforeUnload`。

### 10.4 只读模式

- 触发：版本已发布，或当前用户无 `workflow_modify`。
- 顶栏：`[只读]` 徽标；保存/发布隐藏；保留「版本对比」「导出 JSON」。
- 画布：可平移缩放、可框选查看，不可拖拽节点、不可连线、不可编辑属性。
- 右面板字段全部 disabled，但保留可复制。
- 已发布版本顶部提示条：「已发布版本不可编辑，如需修改请派生草稿」+ 按钮「派生草稿」。

### 10.5 派生草稿

1. 点击「派生草稿」→ 拉取 `GET /api/workflows/{id}/versions`，找 `state = draft` 的版本（可能存在多条，取版本号最大的一条作为"现有草稿"）。
2. **无草稿**：直接 `POST /api/workflows/{id}/versions/{当前版本}/clone`，得到 `latest_version + 1`，跳转新版本编辑器，toast「已创建草稿 v4（基于 v3）」。
3. **已有草稿 v4**：弹窗

```
该工作流已有草稿 v4
[继续编辑 v4]  [以 v3 为基准新建 v5]  [取消]
```

   - 继续编辑（默认聚焦）：直接跳转 v4 编辑器，**不新建版本**。
   - 新建：调 clone（源版本 = 当前查看的版本），版本号为 `latest_version + 1`。
   - 取消：留在当前页。
4. clone 或跳转前，若当前页有未保存修改，先走 10.3 的离开确认。
5. 不自动清理旧草稿；草稿的删除沿用工作流版本管理的既有删除能力（若无则本期不做删除）。

---

## 11. 版本对比（只读 diff）

路由 `/console/workflows/:workflowId/versions/:version/diff/:other`。

### 11.1 布局

```
← 返回  对比 v2 → v3                             [交换 A/B]  [图例]
┌───────────────────────────────────────────────┬─────────────────────┐
│  A: v2（已发布）        B: v3（草稿）           │ 差异（7）           │
│                                               │ 节点 +2  -1  ~3     │
│      [旧图只读，左]      [新图只读，右]          │ 连线 +3  -2         │
│                                               │ ── 节点 ──          │
│                                               │ + 法务审查   [定位]  │
│                                               │ - 人工复核   [定位]  │
│                                               │ ~ 市场研究 岗位变更  │
└───────────────────────────────────────────────┴─────────────────────┘
```

- 两图并排各占 50%，各自独立平移缩放（本期不做联动缩放）。
- 差异计算在前端完成：并发 `GET` 两个版本的 graph 后按 `node_id` / `(from,to)` 比对，不新增后端端点。

### 11.2 视觉

| 状态 | 节点/边表现 |
|---|---|
| 新增（只在 B） | mint 描边 + `+` 角标 |
| 删除（只在 A） | flare 描边 + 50% 透明度 + 删除线 + `-` 角标（渲染在 A 侧原坐标） |
| 修改（同 id 字段不同） | amber 描边 + `~` 角标 |
| 未变 | mute 描边、降低对比 |

- 修改的字段级明细在右栏展开：`岗位：产品经理 → 产品总监`、`超时：72h → 24h`、`扇出：关 → 4`。
- 点击差异项：对应两图同时居中该节点（各自 fit 到该节点），脉冲高亮。
- 无差异：空态「v2 与 v3 无差异」。
- 版本选择器：顶栏两个下拉，可换成同工作流任意两个版本；A/B 交换按钮。

### 11.3 不做

- 不做字段级合并、不做三路 diff、不做"应用差异到草稿"。

---

## 12. 空态、加载态、错误态

| 场景 | 表现 |
|---|---|
| 版本不存在 / 无权限 | 整页卡片：标题「无法打开该版本」+ 原因 + [返回工作流] |
| 图为空（0 节点） | 画布中央引导卡：「从左侧拖入节点开始，或 [一键生成骨架]」（骨架 = start → agent → final_approval） |
| 加载中 | 三栏骨架屏，画布区显示居中 spinner + 「加载版本 v3…」 |
| 保存中 | 顶栏保存按钮 loading，画布不禁用（可继续编辑，避免打断） |
| 后端 5xx | toast + 保留本地草稿，提供「重试」；不自动丢弃改动 |
| 离线（`navigator.onLine=false`） | 顶栏细横幅「网络已断开，修改仅保存在本地」，保存按钮禁用 |

---

## 13. 快捷键

| 快捷键 | 行为 |
|---|---|
| `Ctrl/⌘ + S` | 保存 |
| `Ctrl/⌘ + Z` | 撤销 |
| `Ctrl/⌘ + Shift + Z` / `Ctrl + Y` | 重做 |
| `Delete` / `Backspace` | 删除选中节点或连线 |
| `Ctrl/⌘ + D` | 复制选中节点（偏移 24px，不复制边） |
| `Ctrl/⌘ + A` | 全选节点 |
| `Esc` | 关闭菜单/退出编辑态/清空选择 |
| `Space + 拖拽` | 平移画布 |
| `Ctrl/⌘ + 滚轮` | 缩放 |
| `Shift + 拖拽` | 框选（默认即可，保留兼容） |
| `F` | 适应画布 |
| `L` | 自动布局 |
| `?` | 快捷键帮助浮层 |

输入框聚焦时禁用画布快捷键（Delete/字母键不触发画布操作）。

---

## 14. 与后端的契约

### 14.1 数据模型增量

```sql
-- 019_create_wf_nodes.sql 中追加
pos_x REAL NOT NULL DEFAULT 0,
pos_y REAL NOT NULL DEFAULT 0,
-- 034_final_contract_alignment.sql 新增
wf_versions.revision INTEGER NOT NULL DEFAULT 1
```

`wf_node_transitions` 不变（打回由拓扑推断，条件存 `condition`）。`revision` 属于版本，不属于节点；每次 Graph 保存（含 force）递增。

### 14.2 Graph JSON

```json
{
  "workflow_id": "wf_contract_review",
  "version": 3,
  "state": "draft",
  "revision": 7,
  "updated_at": "2026-11-24T14:02:11Z",
  "nodes": [
    {
      "node_id": "node_start",
      "name": "开始",
      "seq": 1,
      "position_id": null,
      "node_type": "start",
      "prompt_template": null,
      "needs_artifacts_from": [],
      "max_retries": 3,
      "max_loops": 3,
      "timeout_seconds": null,
      "config": {"trigger": {"mode": ["manual", "message"], "cron": null}},
      "pos_x": 120,
      "pos_y": 80
    }
  ],
  "transitions": [
    {
      "from_node_id": "node_start",
      "to_node_id": "node_market",
      "condition": null
    }
  ]
}
```

约定：

- `revision` 为从 1 开始的整数；GET/clone 返回当前值，PUT 必须回传基准值。`updated_at` 只用于展示，JSON 时间统一 ISO 8601 UTC，不参与乐观锁。
- `node_id` 由前端生成，必须匹配 `^[a-z][a-z0-9_]{0,63}$` 且版本内唯一；不合法或重复返回 `E_DUPLICATE_NODE_ID` / `E_INVALID_NODE_ID`。
- `needs_artifacts_from` / `config` 在 API 里是**结构化对象/数组**，DB 里是 JSON 文本，适配层负责序列化。
- `config` 已知键：`fanout: {enabled: bool, size: int}`、`assignee_id`、`seat_id`、`trigger`。未知键原样保留（往返不丢）。
- 节点顺序由 `seq` 决定，仅用于"无坐标时排布"和列表展示，不代表执行顺序。

### 14.3 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/workflows/{id}/versions/{v}/graph` | 返回 Graph JSON；已发布版本同样可读 |
| PUT | `/api/workflows/{id}/versions/{v}/graph` | 仅 draft 可写；body `{graph, revision}`；成功 revision +1；`?force=true` 跳过 revision 比较并写覆盖审计 |
| POST | `/api/workflows/{id}/versions/{v}/validate` | 不落库，返回 `{ok, errors[], warnings[], stats}` |
| POST | `/api/workflows/{id}/versions/{v}/clone` | 复制为新 draft 版本（`latest_version + 1`），返回新 Graph |
| POST | `/api/workflows/{id}/versions/{v}/publish` | 既有端点，发布前服务端强制 validate |

Validate 响应：

```json
{
  "ok": false,
  "errors": [
    {"code": "E_NO_POSITION", "message": "节点「法务审查」未绑定岗位", "node_id": "node_legal"},
    {"code": "E_MIXED_OUT_EDGES", "message": "「市场研究」的出边条件不一致", "node_id": "node_market", "edge": {"from": "node_market", "to": "node_review"}}
  ],
  "warnings": [],
  "stats": {"node_count": 8, "edge_count": 9, "max_depth": 5, "has_cycle": true}
}
```

- 错误码与前端 9.2 完全一致，前端用同一份常量映射文案（后端返回 message 兜底）。
- 结构性错误在 PUT 时返回 400，body 同 errors 结构；语义错误不在 PUT 阻断。

### 14.4 权限与审计

- GET graph / POST validate 为只读操作，控制台有工作流查看权限即可调用；PUT / clone 需 `workflow_modify`；publish 需 `workflow_publish`。
- PUT 写审计：`workflow.graph_save`（workflow_id, version, node_count, edge_count, force）。
- publish 已有审计保留。

---

## 15. 前端落点

```
web/src/pages/console/
  WorkflowEditorPage.tsx          ← 编辑器整页
  WorkflowDiffPage.tsx            ← 版本对比
web/src/components/workflow/editor/
  EditorTopBar.tsx                顶栏（返回/标题/状态/校验/保存/发布/更多）
  NodePalette.tsx                 左侧节点库 + 图概览
  EditorCanvas.tsx                @xyflow/react 封装、连线校验、拖拽落点
  FlowNode.tsx                    6 类节点统一渲染（按 node_type 分支）
  FlowEdge.tsx                    条件/并行/打回样式与标签
  PropertyPanel.tsx               右面板分发
  NodePropertyForm.tsx            节点字段表单
  EdgePropertyForm.tsx            连线字段表单
  ConditionBuilder.tsx            可视化规则树
  ConditionJsonEditor.tsx         JSON 模式
  PromptTemplateEditor.tsx        模板编辑 + 变量插入
  PromptPreview.tsx               实时预览
  ValidationDrawer.tsx            底部校验清单
web/src/lib/workflow/
  graph.ts                        Graph 类型、序列化、前端结构校验
  condition.ts                    规则 ↔ 可读文案、语法校验
  promptVars.ts                   变量白名单（与后端 4.8 对齐）
  diff.ts                         两版本图差异计算
  layout.ts                       BFS 分层自动布局
```

依赖：`@xyflow/react`；JSON 条件编辑用 CodeMirror 6（`@uiw/react-codemirror` + `@codemirror/lang-json`，按需懒加载）。样式需引入 react-flow 基础 CSS，并在 Tailwind 层覆盖为暗色 token（节点边框、背景、MiniMap）；CodeMirror 用 `EditorView.theme` 内联定制，不引主题包。

路由注册：

```tsx
// ConsoleApp.tsx
{nav.workflows && (
  <>
    <Route path="workflows" element={<ConsoleWorkflowsPage can={can} />} />
    <Route path="workflows/:workflowId/versions/:version/editor" element={<WorkflowEditorPage can={can} />} />
    <Route path="workflows/:workflowId/versions/:version/diff/:other" element={<WorkflowDiffPage />} />
  </>
)}
```

---

## 16. 交互验收清单

1. 从版本表进入草稿编辑器，图按 `pos_x/pos_y` 还原；无坐标的旧数据线性排布且可直接编辑。
2. 六类节点可拖入、可改类型、可删除，删除连带边；操作可撤销/重做。
3. 连线创建受 5.2 全部规则约束，非法连线被拒且有明确提示。
4. 成环自动识别为「打回」虚线边；条件边显示规则摘要。
5. 条件构建器与 JSON 双向切换不丢数据；CodeMirror 有语法高亮与错误行标记；非法 JSON 停留 JSON 模式并报错；编辑器内 Ctrl+S 仍能保存、Ctrl+Z 不影响画布撤销栈。
6. 扇出与多出边双向互斥：先开扇出再加第 2 条出边被拒；已有多条出边时扇出开关置灰；校验兜底报 `E_FANOUT_WITH_MULTI_OUT`。
7. prompt 变量插入、未知变量标红、预览实时刷新。
8. 校验清单可点击定位；错误/警告计数与节点角标一致。
9. 保存：dirty 标识正确、409 有重新加载/覆盖两条路径、结构性错误阻断保存。
10. 发布：有 error 不可发布；成功后转只读并提供派生草稿。
11. 未保存离开触发确认；`beforeunload` 生效。
12. 只读模式所有编辑入口禁用，节点不可拖拽。
13. 版本对比正确标出新增/删除/修改与字段级变化，点击可定位，无差异有空态。
14. 1280px 宽度下三栏可用，面板可折叠，画布不被挤压到不可操作。
15. 键盘快捷键齐全，输入框聚焦时不误触画布删除。
16. 派生草稿：无草稿时直接新建 `latest+1`；已有草稿时弹窗三选一，「继续编辑」不产生新版本。
17. 出边混合被拒绝；全部条件边未命中时任务自动终止（cancelled）并记录原因，不静默卡住。
18. start 节点启用定时触发时，cron 为空或非法被校验拦截并定位到节点。
19. 普通节点第 2 条前向入边被拒绝并提示显式 join；回边不误判，后端发布校验同样生效。
20. 终验零回边/一回边均可保存并发布，超过一条回边报 `E_FINAL_REWORK_EDGES`；零回边驳回的 `approval_rejected` 在任务详情可见。
21. Graph 使用整数 revision：正常保存递增，409 显示服务端 revision，force 覆盖仍递增并写审计。
22. 岗位/员工下拉只调用 `/api/options/positions` 与 `/api/options/employees`，响应按 `{items,total,limit,offset}` 解包，不读取完整组织管理接口。

---

## 17. 本轮补充确认（2026-11-24）

以下 8 条已确认，作为实现依据：

1. **扇出与多出边互斥**：扇出节点只允许 1 条出边，不得同时作为条件/并行分支源（`E_FANOUT_WITH_MULTI_OUT`）。需要汇总时用「扇出节点 → `parallel_join`」串联。
2. **多出边禁止混合**：出边 ≥2 时必须全带条件（条件分支）或全不带条件（并行分支），混合报 `E_MIXED_OUT_EDGES`。不设隐式默认分支；全部条件未命中时任务自动终止并记录 `termination_reason = no_matching_branch`。
3. **派生草稿版本号**：始终 `latest_version + 1`；若已有草稿，先弹窗「继续编辑 v4 / 以当前版本为基准新建 v5 / 取消」，选"继续编辑"不新建版本。
4. **版本 diff 由前端计算**：两个 `GET .../graph` 后本地比对，不新增后端端点，Java 不跟进。
5. **JSON 条件编辑器用 CodeMirror 6**：新增 `@uiw/react-codemirror` + `@codemirror/lang-json`，懒加载，暗色主题按现有 token 内联定制，不引主题包。
6. **显式并行汇聚**：多个前向入边只能进入 `parallel_join`；普通节点直接汇聚报 `E_MULTI_IN_REQUIRES_JOIN`，回边不计入。missing 分片补完后由发起人或超管显式重跑 join，不自动推进。
7. **终验回边与终止原因**：终验仅允许零或一条回边；零回边驳回写 `cancelled/approval_rejected`，多条回边报 `E_FINAL_REWORK_EDGES`。
8. **Graph revision**：保存契约统一 `{graph,revision}`，不再使用 `expected_updated_at`；`force=true` 覆盖保存并审计，JSON 时间仍为 ISO UTC。

引擎语义对应关系：[agent-unification-design.md](./agent-unification-design.md) 4.1（扇出/多出边互斥）、4.4（扇出前置条件）、4.6（条件规则与未命中处理）。
