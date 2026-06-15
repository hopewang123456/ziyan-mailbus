# mailbus 问题修复完成清单 — 2026-06-05

## ✅ 已修复

### Bug 类
| # | 问题 | 修复方式 |
|---|------|---------|
| P0-权限不保存 | `handlers_tasks.py` 适配 `{permissions: {...}}` 格式 |
| P0-API Key 继承 | mailbus-boot.sh 自动 ln -sf .env |
| P1-串行队列 | scanner.py `_has_pushed_message()` |
| P1-消息大小限制 | pusher.py 600字截断 + `store/msg-files/` 外置 |
| P1-inbox 筛选 | 已有「待处理/已完成」筛选按钮 |
| P1-待审计 | 跳过 patrol/notice/heartbeat 日常任务 |
| P2-死代码 | 已清理 |
| P2-按钮布局 | `.btn` padding/font-size 缩小 |
| P2-毛玻璃/炫光/星系 | 全部已实现 |
| P2-趋势图 | 30天贝塞尔平滑曲线，通栏展示 |

### 流程缺陷
| # | 问题 | 状态 |
|---|------|------|
| 流水线引擎 | pipeline.py + role_flow.py + scanner 集成 ✅ |
| 灵霄结果检测 | scanner.py `_do_advance` 分支 ✅ |
| 自动推进 | 检测结果文件 → 读 next_role → 推送下一步 ✅ |

### 功能缺失
| # | 问题 | 状态 |
|---|------|------|
| Token 统计 | Dashboard 统计 tab 已实现 ✅ |
| 巡检日报展示 | API + 前端 + Markdown 渲染 ✅ |
| 子言任务看板 | 团队状态 + 我的任务 ✅ |
| 双子星 Logo | 左侧导航顶部 ✅ |
| i18n | `applyLang()` + `I18N` 映射表已实现 ✅ |
| 机器人头像 | `robotSvg(color)` 已实现 ✅ |

## ❌ 待根治（框架问题，mailbus 无法完全解决）

| # | 问题 | 方案 |
|---|------|------|
| 灵霄 auto-ack | `plans/fix-lingxiao-auto-ack.md` 混合模式（推送文件路径 + 写结果文件）|
| chat -q 超时 | pusher.py 异步推送 + 自动截断，但 agent 框架本身的行为无法控制 |

## 未做（P2 优化，优先级低）
- 子言专属 log（可以利用搜索功能，不是必须独立板块）
- 告警记录完善（需要定义更多告警事件）
