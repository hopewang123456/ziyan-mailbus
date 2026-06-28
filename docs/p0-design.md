# 任务流水线引擎 — 细化设计 v2

---

## 核心原则

1. **自动流转** — mailbus scan 检测到当前步骤完成，自动触发下一步，不依赖 agent 自觉
2. **最小改动也要测试** — 没有"不需要测试"的改动。小改动由验收方（小七）测试，大改动由灵验做完整回归
3. **每步有输出** — 每个步骤完成后必须产出工单（审查结论、测试报告、验收记录），可供点击查看
4. **超时有升级机制** — 不无限等待

---

## 流水线模板

根据任务规模，支持不同的流水线模板：

### 模板 A：完整流程（代码改动）

```
灵昭发任务
  ↓
① 开发（灵霄/大力）
    → 产出：代码改动的 git diff + 自测结果
    ↓ 自动触发（大力回复"完成"后）
② 审查（灵鉴）
    → 产出：审查结论（通过 / 不通过 + 问题列表）
    ↓ 自动触发（灵鉴回复"通过"后）
③ 测试（灵验 — 大改动 / 小七 — 小改动）
    → 产出：测试报告（PASS / FAIL + 逐项结果）
    ↓ 自动触发（测试回复"全部PASS"后）
④ 验收（小七）
    → 产出：验收结论（已验收，可上线 ✅）
    ↓ 自动触发
⑤ 上线（完成）
```

### 模板 B：轻量流程（配置/文档改动）

```
灵昭发任务
  ↓
① 修改（灵霄/大力）
    ↓ 自动触发
② 审查（灵鉴）
    ↓ 自动触发
③ 验收（小七 — 兼任测试）
    ↓ 自动触发
④ 上线
```

### 模板 C：纯审查（不需要开发的审查任务）

```
灵昭发任务
  ↓
① 审查（灵鉴）
    ↓ 自动触发
② 测试（灵验 / 小七）
    ↓ 自动触发
③ 验收（小七）
```

---

## 流转机制细化

### 状态定义

| 状态 | 含义 | 触发条件 |
|------|------|----------|
| `pending` | 等待中 | 上一步未完成 |
| `running` | 正在执行 | 上一步完成后自动设为 running，并推消息给 assignee |
| `waiting_reply` | 等待回复 | 消息已推送给 assignee，等待 ta 回复 |
| `completed` | 已完成 | assignee 回复了结论 |
| `failed` | 失败 | assignee 回复"不通过"或审查发现问题 |
| `skipped` | 跳过 | 超时 3 次催办无回复 |
| `cancelled` | 取消 | 中途取消整条任务 |

### 完整状态机

```
pending → running → waiting_reply → completed → 下一步 pending
                                ↘ failed → 通知灵昭介入
                                ↘ timeout x3 → skipped → 下一步 pending
```

### scan 检测逻辑

每次 scan 时，对每条有 pipeline 的任务：

```python
for task in tasks_with_pipeline:
    current = task.get_current_step()  # status=running 的那一步
    
    # 检查当前步骤的 assignee 有没有新回复
    if current["status"] == "waiting_reply":
        reply = check_reply(task["task_id"], current["assignee"])
        
        if reply and is_conclusive(reply):
            # 有实质回复 → 标记完成
            mark_step_done(task, current, reply)
            
            # 自动触发下一步
            next_step = get_next_step(task, current)
            if next_step:
                start_step(task, next_step)
                send_message_to_assignee(next_step)
            else:
                # 没有下一步了 → 整条任务完成
                mark_task_done(task)
        
        elif reply and is_failure(reply):
            # 回复不通过 → 标记失败，通知灵昭
            mark_step_failed(task, current, reply)
            notify_lingzhao(task, current, reply)
        
        elif is_timeout(current):
            # 超时 → 催办
            remind(current)
            if current["remind_count"] >= 3:
                # 催 3 次无回复 → 跳过
                skip_step(task, current)
                notify_lingzhao(task, current, "已跳过")
                # 走下一步
                next_step = get_next_step(task, current)
                if next_step:
                    start_step(task, next_step)
```

### 谁来确定"回复有效"

不是 agent 的所有回复都能触发流转。只有**包含实质结论的回复**才算完成：

| 步骤 | 什么算"完成" | 什么算"不通过" |
|------|-------------|---------------|
| 开发 | 回复内容包含"已完成"或"做好了"或 git diff 信息 | 回复"做不了"或"有问题" |
| 审查 | 回复包含"通过"或"APPROVED" | 回复包含"不通过"或"有问题需要修复" |
| 测试 | 回复包含"PASS"或"全部通过" | 回复包含"FAIL"或"测试失败" |
| 验收 | 回复包含"已验收"或"可上线" | 回复包含"验收不通过" |

检测方式：`is_conclusive(reply)` 检查回复文本中是否包含关键词。

---

## Dashboard 展示

### 任务列表页

每条任务卡片下方显示流水线进度条：

```
┌──────────────────────────────────────────────────┐
│ 🎨 Dashboard 重设计第一批                        │
│ ID: msg-xxx · 发起人: 灵昭 · 23:00              │
│                                                  │
│ [开发 ✅] ─→ [审查 ⏳] ─→ [测试 ⏸] ─→ [验收 ⏸]  │
│                                                  │
│ 当前: 灵鉴审查中 (已等待 5 分钟)                 │
│ 催办: 0/3                                        │
└──────────────────────────────────────────────────┘
```

### 节点点击弹窗

点击每个节点，展示该步骤的工单内容：

```
┌─ 审查工单 ─────────────────────────────────────┐
│                                                 │
│ 步骤: 审查                                       │
│ 执行人: 灵鉴                                     │
│ 状态: ✅ 已完成                                  │
│ 时间: 2026-06-04 12:00 ~ 12:15                  │
│                                                 │
│ 审查结论: 通过 ✅                                │
│ 发现问题: 2 个（一般 1, 建议 1）                │
│                                                 │
│ 📄 查看完整审查报告                              │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 超时和异常处理

| 场景 | 处理 |
|------|------|
| 当前步骤 10 分钟无回复 | mailbus 发催办消息给 assignee，remind_count+1 |
| 催办 3 次无回复 | 跳过该步骤 + 通知灵昭"xxx 步骤已超时跳过，请关注" |
| 步骤回复"不通过" | 标记 failed + 通知灵昭 + pipeline 暂停 |
| 灵昭手动推进 | `POST /api/tasks/<id>/pipeline/advance` — 强制推进到下一步 |
| 灵昭手动跳过 | `POST /api/tasks/<id>/pipeline/skip` — 跳过当前步骤 |
| 灵昭手动取消 | `POST /api/tasks/<id>/pipeline/cancel` — 整条取消 |

---

## 需要改的模块

| 文件 | 改动内容 |
|------|----------|
| `lib/models.py` | Message 新增 `pipeline` 字段 |
| `lib/pipeline.py` | 新增文件：PipelineEngine 类，管理状态机、流转、催办、跳过 |
| `lib/scanner.py` | scan 时调 PipelineEngine.check() |
| `lib/pusher.py` | 生成步骤消息时套用 template |
| `lib/api/base.py` | 注册 `/api/tasks/<id>/pipeline/*` 路由 |
| `docs/index.html` | 任务卡片下方流水线进度条 + 节点弹窗 |
