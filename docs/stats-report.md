# mailbus 消息统计/报表方案

## 目标

Dashboard 新增一个「📊 统计」tab，展示平台运行数据。

---

## 1. API 接口

### `GET /api/stats` — 平台统计数据

返回聚合统计数据：

```json
{
  "period": "7d",
  "token_usage": {
    "total": 15840000,
    "by_agent": {
      "lingzhao": {"tokens": 5200000, "pct": 32.8},
      "lingxiao": {"tokens": 4100000, "pct": 25.9},
      "xiaoqi":   {"tokens": 2800000, "pct": 17.7},
      "lingjin":  {"tokens": 1500000, "pct": 9.5},
      "lingxi":   {"tokens": 1200000, "pct": 7.6},
      "dali":     {"tokens": 800000,  "pct": 5.1},
      "yige":     {"tokens": 240000,  "pct": 1.4}
    }
  },
  "messages": {
    "total": 847,
    "by_type": {"task": 320, "notice": 280, "reply": 200, "forward": 47},
    "by_agent_received": {
      "lingxiao": 145, "xiaoqi": 132, "lingjian": 98, ...
    }
  },
  "tasks": {
    "total": 320,
    "by_status": {"success": 210, "failed": 45, "timeout": 38, "running": 27},
    "by_agent": {
      "lingxiao": {"total": 85, "success": 62, "failed": 12, "timeout": 11},
      "xiaoqi":   {"total": 72, "success": 58, "failed": 8, "timeout": 6}
    },
    "avg_response_minutes": {
      "lingxiao": 4.2,
      "xiaoqi":   3.8,
      "lingjin":  12.5,
      "dali":     6.1
    }
  },
  "skills": {
    "total_skills": 85,
    "by_agent": {
      "lingzhao": {"loaded": 9, "used": 7, "top_skill": "tarot-beginner", "top_count": 42},
      "lingxiao": {"loaded": 5, "used": 3, "top_skill": "writing-plans", "top_count": 18}
    }
  },
  "trend": {
    "last_7_days": [
      {"date": "2026-05-28", "messages": 45, "tasks": 18},
      {"date": "2026-05-29", "messages": 62, "tasks": 25}
    ]
  }
}
```

---

## 2. 数据来源

大多数数据可以从现有数据源计算，不需要额外存储：

| 指标 | 数据源 | 计算方式 |
|------|--------|----------|
| 消息量 | 各 agent inbox.json | count messages |
| 任务状态 | tracker list_all() | count by status |
| 响应时间 | inbox messages created_at → acknowledged_at | 计算差值均值 |
| 超时/失败 | tracker timeout/failed count | count |
| 趋势 | inbox messages created_at 按天分组 | group by date |
| Skill 使用 | skill-usage.json | 已有 |
| Token | Hermes session DB / 外部估算 | 需接入 |

Token 数据目前没有直接记录在 mailbus 中。有两个方案：
- **方案 A**：每次调用 Hermes chat -q 时记录 token 消耗到 `store/token-usage.jsonl`
- **方案 B**：只在 dashboard 展示已知数据，token 数据后续再接

建议先做方案 B（已有的数据先展示），方案 A 后续再补。

---

## 3. Dashboard 页面

```
┌──────────────────────────────────────────────────┐
│ 📊 统计  ·  过去 7 天     [▼ 7天] [▼ 30天]    │
├──────────────────────────────────────────────────┤
│                                                  │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐           │
│  │ 💬   │ │ ✅   │ │ ⏳   │ │ ❌   │           │
│  │ 消息  │ │ 完成  │ │ 超时  │ │ 失败  │           │
│  │ 847  │ │ 210  │ │ 38   │ │ 45   │           │
│  └──────┘ └──────┘ └──────┘ └──────┘           │
│                                                  │
│  ── Agent 排行 ──────────────────────────────     │
│                                                  │
│  🎯 灵霄  85 任务  62✅ 12❌ 11⏱   avg 4.2m  │
│  ████████████████████░░░░  72%                  │
│  🦞 小七  72 任务  58✅  8❌  6⏱   avg 3.8m  │
│  ██████████████████░░░░░░  80%                  │
│  🔍 灵鉴  48 任务  40✅  5❌  3⏱   avg 8.5m  │
│  ████████████░░░░░░░░░░░░  83%                  │
│                                                  │
│  ── 消息趋势（近7天） ───────────────────────      │
│                                                  │
│  60 ┤        ▄                                 │
│  50 ┤   ▄    █ ▄     ▄                          │
│  40 ┤   █ ▄  █ █  ▄  █ ▄                       │
│  30 ┤   █ █  █ █  █  █ █  ▄                    │
│     └──────────────────────────                 │
│       28  29  30  31  01  02  03                │
│                                                  │
│  ── Skill 使用排行 ────────────────────────      │
│                                                  │
│  1.  tarot-beginner        42 次  🪷灵昭        │
│  2.  design-frontend       28 次  🪷灵昭        │
│  3.  writing-plans         18 次  🎯灵霄        │
│  4.  requesting-code-review 12 次 🔍灵鉴        │
│  5.  codebase-inspection    8 次  🔍灵鉴        │
│                                                  │
│  ── Agent Skill 详情（展开） ───────────────     │
│                                                  │
│  🪷 灵昭  ·  加载 9 个 skill  ·  使用 7 个     │
│  [tarot-beginner] [tarot-intermediate] ...       │
│  [design-frontend] [ui-ux-design] ...            │
│                                                  │
└──────────────────────────────────────────────────┘
```

---

## 4. 实施内容

1. `lib/api/handlers_system.py` — 新增 `handle_stats()` 计算聚合数据
2. `lib/api/base.py` — 注册 `/api/stats` 路由
3. `docs/index.html` — 新增「📊 统计」导航 tab + 内容区
4. `docs/index.html` — 新增 `renderStatsTab()` 渲染函数

---

## 5. 验收标准

□ 统计 tab 显示总消息数、完成任务数、超时数、失败数
□ Agent 排行按任务数排序，显示成功率 + 平均响应时间
□ 消息趋势图（近 7 天柱状图）
□ Skill 使用排行
□ 点开 agent 可查看其加载的 skill 列表
□ 时间范围切换（7天 / 30天）
