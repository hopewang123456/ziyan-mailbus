# 「👑 子言」专属面板 — 实施设计方案

## 一、概述

在 mailbus dashboard 新增一个「👑 子言」tab，放在导航栏最前。该面板聚合子言关心的四类信息：
1. 待确认事项
2. 最近告警摘要
3. 团队状态一览
4. 最近完成任务

**目标文件**：`docs/index.html`（单文件修改，约 +150 行）

---

## 二、修改清单

### 2.1 导航栏新增 tab（放在最前面）

**位置**：`<div class="tabs">` 第一项

```html
<div class="tab active" data-tab="ziyan" onclick="switchTab('ziyan')"><span class=icon3d>👑</span> 子言</div>
```

> 注意：原来的 `overview` tab 从 active 改为非 active，因为新 tab 放第一个且默认激活。

**影响**：原先 `overview` tab 是 `class="tab active"`。改为 `class="tab"`。

### 2.2 新增 tab-content 容器

**位置**：放在第一个 tab-content（原 overview 之前）

```html
<!-- Tab: 子言专属面板 -->
<div class="tab-content active" id="tab-ziyan">
  <div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center">
    <span style="font-size:13px;color:#94a3b8" id="ziyanSummary"></span>
    <button class="btn btn-sm" onclick="renderZiyanTab()">🔄 刷新</button>
  </div>
  <div id="ziyanContent"></div>
</div>
```

### 2.3 新增 CSS 片段

在 `<style>` 区域内（约第 126-127 行附近），无需新增样式——复用已有的 `.stat-card`、`.table`、`.badge-*` 即可。

### 2.4 新增 JS 函数

#### `renderZiyanTab()`

数据源（loadAll 已有）+ 专有请求：
- `rawData.tasks` — 已有（loadAll 已加载）
- `rawData.alerts` — 已有
- `rawData.status` — 已有（含 agent_statuses）
- 额外请求 `/api/inbox/lingzhao` — 获取子言的待确认事项
- 额外请求 `/api/tasks`（已加载）

#### 四个渲染区域

结构：

```html
<div id="ziyanContent">
  <!-- 1. 待确认事项 -->
  <div class="stat-card" style="margin-bottom:12px">
    <h3>📋 待确认事项 <span id="pendingCount" style="font-size:12px;color:#64748b;font-weight:400"></span></h3>
    <div id="ziyanPendingList"></div>
  </div>
  
  <!-- 2. 最近告警摘要 -->
  <div class="stat-card" style="margin-bottom:12px">
    <h3>🔔 最近告警 <span id="alertSummary" style="font-size:12px;color:#64748b;font-weight:400"></span></h3>
    <div id="ziyanAlertSummary"></div>
  </div>
  
  <!-- 3. 团队状态一览 -->
  <div class="stat-card" style="margin-bottom:12px">
    <h3>👥 团队状态</h3>
    <div id="ziyanTeamStatus"></div>
  </div>
  
  <!-- 4. 最近完成任务 -->
  <div class="stat-card">
    <h3>✅ 最近完成任务</h3>
    <div id="ziyanRecentTasks"></div>
  </div>
</div>
```

---

## 三、各区域数据来源与渲染逻辑

### 3.1 待确认事项

**数据源**：`/api/inbox/lingzhao`（子言自己的 inbox）

筛选逻辑：
- `type === "task"` 且 `status !== "acknowledged"`（未确认的任务）
- 或 content 中包含「请确认」「需确认」「请求审批」「请示」等关键词的消息
- 按 created_at 降序排列

渲染为卡片列表，每个卡片显示：
- 发件人（from）+ 时间
- 内容预览（截断至 80 字符）
- 点击可直接跳转到邮箱查看

UI 样式（复用现有 msg-item）：

```html
<div class="msg-item unread" style="cursor:pointer" onclick="switchTab('agents')">
  <div class="head">
    <span>📩 来自 {from}</span>
    <span>{time}</span>
  </div>
  <div class="body">{content_preview}</div>
</div>
```

**无数据时**：显示「✅ 暂无待确认事项」绿色提示。

### 3.2 最近告警摘要

**数据源**：`rawData.alerts.alerts`

筛选逻辑：
- 按 created_at 降序排列
- 取前 5 条
- 按 severity 着色：critical=红, warn=黄, info=蓝

渲染为简洁表格（不展示全量告警表格的"ID"列，只展示关键信息）：

```
级别 | Agent | 消息 | 时间
```

**交互**：最后一行加「查看全部 →」按钮，点击跳转到告警 tab。

**无数据时**：显示「🎉 无告警，系统平稳运行」

### 3.3 团队状态一览

**数据源**：`rawData.status.agent_statuses` + `rawData.agents.agents`

逻辑：
- 遍历所有 agent
- 展示：名称、类型、在线状态（从 heartbeat 数据推断）、未读消息数
- 在线状态判定：`rawData.hb` 中的 `status` 或 agent 的 last_heartbeat < 5min

渲染为紧凑网格卡片（3×N 布局）：

```html
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
  {每个 agent 一个卡片}
</div>
```

每个卡片（复用 agent-card 小尺寸版）：
```
🪷 灵昭 (lingzhao)
● online  ·  5条未读
📬 查看邮箱
```

**交互**：点击名称进入 agent 详情；点击「📬 查看邮箱」进入邮箱。

### 3.4 最近完成任务

**数据源**：`rawData.tasks.tasks`

筛选逻辑：
- status === "success"
- 按 created_at 降序排列
- 取前 5 条

渲染为简洁列表，每项显示：
- 任务 ID（短版：取后 6 位）
- 概要
- 完成时间

```html
<div style="display:flex;flex-direction:column;gap:4px">
  <div class="msg-item" style="padding:6px 10px;display:flex;justify-content:space-between;align-items:center">
    <span>✅ #{task.task_id.slice(-6)} {task.summary}</span>
    <span style="font-size:10px;color:#64748b">{task.updated_at}</span>
  </div>
</div>
```

**无数据时**：显示「📭 暂无已完成任务」

---

## 四、加载时序

### 方案 A（推荐）：在现有 loadAll 末尾加入

`loadAll()` 已加载了 tasks、alerts、status、agents 等所有数据。只需在 `loadAll()` 最后加入：

```javascript
// 子言面板
renderZiyanTab();
```

修改说明：
- `reloadData()` 函数中新增 `ziyan` 分支，在 tab 切换时也刷新

### 方案 B：独立请求

若希望子言面板不阻塞主加载，额外 fetch `/api/inbox/lingzhao` 单独请求。

**推荐方案 A**，减少冗余请求，且 inbox/lingzhao 的数据由 loadAll 中的现有数据也可部分覆盖。

---

## 五、交互细节

1. **待确认事项**的每一项点击后，跳转到 Agent 邮箱 tab（自动定位到该 agent）
2. **最近告警摘要**的「查看全部」跳转到告警 tab
3. **团队状态**中的 agent 名称点击，打开 agent 详情弹窗（复用 `showAgent(name)`）
4. **自动刷新**：子言面板跟随 `autoRefreshChk` 的 30s 自动刷新

---

## 六、代码修改位置汇总

| 操作 | 文件位置（行号约） | 内容 |
|------|------------------|------|
| 插入导航 tab | L379 前 | `<div class="tab active" data-tab="ziyan"...>` |
| 调整 overview tab | L380 | `class="tab"` (去掉 active) |
| 插入 tab-content | L389 前 | `<div class="tab-content active" id="tab-ziyan">...` |
| 调整 overview tab-content | L390 | `class="tab-content"` (去掉 active) |
| 新增 JS 函数 | 末尾 `</script>` 前 | `renderZiyanTab()` 约 80 行 |
| 修改 loadAll() | 末尾加 | `renderZiyanTab();` |
| 修改 reloadData() | 加 ziyan 分支 | 无需额外 API |
| 修改 switchTab 默认 | 初始激活 | 自动切到 ziyan |

---

## 七、实施步骤（给小七的指令）

1. 打开 `docs/index.html`
2. 在 `<div class="tabs">` 的**最前面**插入子言 tab
3. 把 overview 的 `active` 去掉
4. 在第一个 tab-content 位置（原 L390 之前）插入子言面板 HTML
5. 把原 overview tab-content 的 `active` 去掉
6. 在 `</script>` 前插入 `renderZiyanTab()` 函数
7. 在 `loadAll()` 末尾（`toast('已刷新')` 之前）加入 `renderZiyanTab()`
8. 测试：刷新页面，确认子言 tab 默认激活，四个区域正常显示

---

## 八、效果预览（文字描述）

切换页面后，第一眼看到的是「👑 子言」tab：

```
👑 子言 | 📊 总览 | 🤖 Agent(9) | 📢 公告栏 | 🎯 任务追踪 | 🔍 审查 | 💓 健康状态 | 🔔 告警

┌─ 📋 待确认事项 ──────────────────────────────┐
│ 📩 来自 lingxi · 10:23                       │
│ 关于 OpenClaw 版本升级方案，请确认是否现在执行 │
│                                              │
│ 📩 来自 lingjin · 昨天 16:45                  │
│ 安全审计报告已出，请审批是否修复所有中危漏洞    │
└──────────────────────────────────────────────┘

┌─ 🔔 最近告警 ────────────────────────────────┐
│ 🔴 critical · lingxi · 内存使用超 90%  → 10:25│
│ 🟡 warn · yige · 心跳延迟 > 30s  → 10:20    │
│ 🔵 info · 系统 · mailbus 自动恢复  → 09:15  │
│                                       查看全部→ │
└──────────────────────────────────────────────┘

┌─ 👥 团队状态 ──── 3×3 网格 ────────────────┐
│ 🪷 灵昭  ● online  5未读 │ 🦋 灵瑾  ● online  0 │
│ 🔭 灵犀  ⚪ offline  —   │ 🔍 灵鉴  ● online  2 │
│ 🧪 灵验  ● online  0   │ 🤖 大力  ● online  — │
│ 🎯 灵霄  ● online  —   │ 🦞 小七  ● online  3 │
│ 👨‍🔧 一哥  ⚪ offline  —   │                        │
└──────────────────────────────────────────────┘

┌─ ✅ 最近完成任务 ────────────────────────────┐
│ ✅ #79618 邮件模板优化 · 10:30               │
│ ✅ #79615 修复心跳超时误报 · 09:45           │
│ ✅ #79610 公告栏权限功能 · 昨天 17:20        │
└──────────────────────────────────────────────┘
```
