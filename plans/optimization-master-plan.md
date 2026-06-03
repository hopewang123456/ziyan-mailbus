# mailbus 优化方案 — 全部汇总 & 派工计划

> 2026-06-03 · 所有优化点讨论完毕，准备统一派工

---

## 已派工（执行中）

| 优先级 | 内容 | 执行者 | 方案文档 |
|--------|------|--------|----------|
| P0 | API Key 继承机制 | 灵霄 | `plans/2026-06-03-bug-fix-plan.md` |
| P1 | 推送消息 system context 精简 | 灵霄 | `plans/2026-06-03-bug-fix-plan.md` |
| P2 | 串行消息队列 | 灵霄 | `plans/task-audit-redesign.md` 第五节 |
| P3 | 灵鉴启动脚本技能名修正 | 灵霄 | `plans/2026-06-03-bug-fix-plan.md` |
| P4 | 前端死代码清理 + 状态细化 | 小七/灵霄 | `plans/2026-06-03-bug-fix-plan.md` |

---

## 待派工

### A — 规则文档外置 + 模板系统

| 子项 | 内容 | 执行者 |
|------|------|--------|
| A1 | `lib/pusher.py` 精简 system context 为 15 行，只保留规则路径 | 灵霄 |
| A2 | 推送消息格式改为引用规则文档路径 | 灵霄 |
| A3 | 规则变更时自动广播通知 affected agent | 灵霄 |
| A4 | 建 `store/templates/` 目录，写常用消息模板 | 灵昭 |
| A5 | 推送时附带模板路径，agent 参考模板回复 | 灵霄 |

**方案文档：** `plans/2026-06-03-optimization-brainstorm.md`、`store/rules/*.md`
**规则文件已有：** `common.md`、`reviewer.md`、`tester.md`、`developer.md`、`dispatcher.md`

---

### B — 消息搜索

| 子项 | 内容 | 执行者 |
|------|------|--------|
| B1 | `lib/api/base.py` 注册 `GET /api/search` 路由 | 灵霄 |
| B2 | `lib/api/handlers_system.py` 加 `handle_search()` | 灵霄 |
| B3 | `lib/scanner.py` scan 时自动调用 `scan_and_index()` 建 FTS5 索引 | 灵霄 |
| B4 | Dashboard 导航栏加搜索框 + 搜索结果弹窗 | 小七 |

**方案文档：** 当前对话记录

---

### C — Dashboard 重设计（科技感 UI）

| 子项 | 内容 | 执行者 |
|------|------|--------|
| C1 | 引入 CSS 变量系统（冷色调配色） | 大力 |
| C2 | 深色渐变背景 + 星系粒子 + 银河光带 | 大力 |
| C3 | 鼠标炫光跟随动效 | 大力 |
| C4 | 左侧固定导航栏（飞船 Logo、轨道环动画） | 大力 |
| C5 | 毛玻璃卡片样式 + 发光边框 | 大力 |
| C6 | 霓虹灯管状态文字 + 赛博元素 | 大力 |
| C7 | 全息网格 + 数据流动线 + 脉冲扫描环 + 能量护盾边框 | 大力 |
| C8 | Agent 头像改为机器人 SVG | 大力 |
| C9 | 加载动画（飞船飞行、星云脉冲环） | 大力 |

**方案文档：** `plans/dashboard-redesign.md`

---

### D — 消息统计/报表

| 子项 | 内容 | 执行者 |
|------|------|--------|
| D1 | `GET /api/stats` 接口（聚合消息量、任务状态、响应时间、趋势） | 灵霄 |
| D2 | Dashboard 新增「📊 统计」tab | 小七 |
| D3 | Agent 排行（成功率、平均响应时间） | 小七 |
| D4 | 消息趋势柱状图 | 小七 |
| D5 | Skill 使用排行 + Agent Skill 详情 | 小七 |

**方案文档：** `plans/stats-report.md`

---

### E — 归档机制启用

| 子项 | 内容 | 执行者 |
|------|------|--------|
| E1 | `lib/scanner.py` scan 时调用 `archive_all()` | 灵霄 |
| E2 | 归档周期改为 3 天（改 `archive_days` 参数） | 灵霄 |
| E3 | Dashboard 显示"已归档 N 条"提示 | 小七 |

**方案文档：** `lib/archiver.py`（代码已有，仅需调用）

---

## F — 灵巡（巡检官）上线

| 子项 | 内容 | 执行者 |
|------|------|--------|
| F1 | 启动灵巡的 Hermes dashboard（port 9125） | 灵昭（已做完） |
| F2 | 给灵巡配 mailbus 定时巡检 cron（每 15 分钟执行一次巡检） | 灵霄 |
| F3 | 灵巡每天生成日报，写入 `store/reports/daily/<date>.md` | 灵霄 |
| F4 | Dashboard 新增「📋 巡检日报」tab，展示灵巡的日报内容 | 小七 |

**规则文件：** `store/rules/patroller.md`
**Profile：** `/mnt/e/hermes-data/.hermes/profiles/lingxun/`

---

## 执行顺序（更新版）

```
第一批（灵霄）:
  已派的 P0-P4 → A1-A3 → B1-B3 → D1 → E1-E2 → F2-F3

第二批（小七，等灵霄后端完成）:
  P4（死代码清理）→ B4 → D2-D5 → E3 → F4

第三批（大力，等小七调度）:
  C1-C9（dashboard 重设计）
```

## 验收流程

每个子项完成后：
1. 🔍 灵鉴审查代码
2. 🧪 灵验回归测试
3. 通过后才算完成
