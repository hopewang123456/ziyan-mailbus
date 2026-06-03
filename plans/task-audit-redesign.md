# 任务追踪 + 审计面板重设计

## 痛点分析

### 当前问题
1. **任务列表按文件名排序（os.listdir），不是按时间倒序** — 最新的任务不在最上面
2. **任务追踪（tracker）和审查报告（reports）是两个独立的系统** — 同一件事的"灵霄做→灵鉴审查"无法关联展示
3. **审查报告没有关联到具体任务** — 审查报告只是一堆 markdown 文件，不知道是哪个任务触发的
4. **仪表盘的"任务追踪"和"审查报告"是两个分离的 tab** — 子言需要来回切换看

### 目标
1. ✅ 最新的任务在最上面
2. ✅ 审计结果与任务绑定展示（灵鉴审查后的结果直接在任务下面展现）
3. ✅ 子言在同一个页面看到"谁在做什么 + 审计结果"

---

## 设计

### 一、后端改动 (lib/tracker.py)

#### 1. 任务倒序

修改 `list_all()` 让最新的在上面：

```python
def list_all(self, status_filter: str = None) -> list:
    results = []
    for fname in os.listdir(self.tasks_dir):
        if fname.endswith(".json"):
            task = json_read(...)
            if task and (not status_filter or task.get("status") == status_filter):
                results.append(task)
    # 按 updated_at 倒序（最新的在最上面）
    results.sort(key=lambda t: t.get("updated_at", t.get("created_at", "")), reverse=True)
    return results
```

#### 2. 任务记录审计结果

新字段 `audit_log: [{reviewer, result, issues, summary, file, at}]`

```python
def add_audit(self, task_id: str, reviewer: str, result: str,
              issues: list = None, summary: str = "", report_file: str = ""):
    """追加审计记录"""
    task = self.get(task_id)
    if not task:
        return None
    if "audit_log" not in task:
        task["audit_log"] = []
    task["audit_log"].append({
        "reviewer": reviewer,      # lingjian / lingjin
        "result": result,          # pass / fail / warn
        "issues": issues or [],
        "summary": summary,
        "report_file": report_file,  # 指向 store/reports/xxx.md
        "at": _now_iso(),
    })
    task["updated_at"] = _now_iso()
    # 如果审计失败，自动标记任务为 failed
    if result == "fail":
        task["status"] = TaskStatus.FAILED
    json_write(self._task_path(task_id), task)
    return task
```

#### 3. 任务创建时自动关联 review 报告

新函数 `find_reviews_for_task(task_id)` — 扫描 `store/reports/` 目录，将文件名包含 task_id 的报告自动关联。

或者更简单：在审查报告中通过 `review.py` 等工具生成 report 时，如果关联了某个 task_id，就在报告文件的 YAML frontmatter 或文件名中加入 `task_id` 标记。

当前方案：**审查报告文件名包含任务 id 即可自动关联**。例如 review 报告 `review-xxx.md` 如果命中了某个 task_id，后端 `/api/tasks` 返回时自动嵌入。

---

### 二、新增 API

#### 1. /api/tasks/audit — POST 追加审计记录

```json
// 请求
POST /api/tasks/audit
{
  "task_id": "msg-20260603-xxxxx",
  "reviewer": "lingjian",
  "result": "pass",
  "issues": [{"severity": "low", "desc": "变量命名建议优化"}],
  "summary": "代码无安全问题，建议优化命名",
  "report_file": "review-20260603-011651.md"
}
```

#### 2. /api/tasks/summary — GET 聚合视图

返回所有任务，每个任务带关联的审计记录和关联的审查报告：

```json
{
  "tasks": [
    {
      "task_id": "msg-20260603-xxxxx",
      "summary": "安全中风险 M1-M4 修复",
      "assignee": "lingxiao",
      "status": "success",
      "audit_log": [
        {
          "reviewer": "lingjian",
          "result": "pass",
          "issues": [],
          "summary": "代码审查通过，无安全问题",
          "at": "2026-06-03T15:00:00+0800"
        }
      ],
      "updated_at": "2026-06-03T15:00:00+0800"
    }
  ]
}
```

现有 `/api/tasks` 接口可以直接返回 audit_log 字段（已经在 tracker 里扩充了），前端按 updated_at 倒序渲染。

### 三、前端改动 (docs/index.html)

#### 合并"任务追踪"和"审查报告"为一个 tab

**新的「📋 任务审计」tab**，取代原来分离的"任务追踪"+"审查报告"两个 tab。

**页面结构：**

```
┌─ 顶部筛选栏 ─────────────────────────┐
│ [全部] [进行中] [已完成] [失败] [待审计] │  ← filter 按钮
└─────────────────────────────────────────┘

┌─ 任务卡片列表（每条最新在最上面） ──────┐
│                                         │
│ ▸ 安全中风险 M1-M4 修复                 │
│   ID: msg-xxx · 负责人: 灵霄🔭           │
│   状态: ✅ 成功 · 更新时间: 15:00       │
│                                         │
│   ┌─ 审计记录 ─────────────────────┐    │
│   │ 🔍 灵鉴 · ✅ 通过 · 15:00      │    │
│   │ 代码审查通过，无安全问题         │    │
│   │ [查看完整报告]                  │    │
│   └─────────────────────────────────┘    │
│                                         │
│ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
│                                         │
│ ▸ session 中途失效验证 (P0)              │
│   ID: msg-yyy · 负责人: 灵霄🔭           │
│   状态: ⏳ 运行中 · 更新时间: 14:30      │
│   追踪链: 灵昭发起 → 灵霄执行           │
│                                         │
└─────────────────────────────────────────┘
```

**交互细节：**
- 每条任务卡片可折叠展开，默认展开最近的 5 条
- 审计记录如果有，直接在卡片下方展示
- 审计记录里的"查看完整报告"弹窗显示完整 markdown
- 筛选栏切换显示不同状态的任务

**数据流：**
1. `GET /api/tasks` → 返回任务列表（带 audit_log）
2. `GET /api/reports` → 返回审查报告列表（用于审计记录中的"查看完整报告"）
3. 前端 `sort by updated_at DESC` → 最新的在最上面

### 四、不需要改的

- `/api/reports` 保留（审查报告独立存储为 md 文件）
- `/api/reviews` 保留（代码审查报告按项目分组）
- 审查报告的生成流程（review.py / watcher）不改
- 审计员（灵鉴/灵瑾）的审查流程不变——他们审查完后通过 API 追加审计记录

---

## 执行计划

| 步骤 | 内容 | 执行者 |
|------|------|--------|
| 1 | `tracker.py`: 改 `list_all()` 按 updated_at 倒序（注意 +0800 时区格式的排序） | 灵霄 |
| 2 | `tracker.py`: 加 `add_audit()` 方法 | 灵霄 |
| 3 | `handlers_tasks.py`: 加 `handle_task_audit()` POST 路由 | 灵霄 |
| 4 | `base.py`: 注册 `/api/tasks/audit` 路由 | 灵霄 |
| 5 | `index.html`: 合并任务+审查为一个 tab，任务卡片布局 + 审计记录展示 | 小七 |
| 6 | 测试审计流程：创建任务→灵霄执行→灵鉴审查追加审计记录→前端展示 | 灵验 |

---

## 五、串行队列派发（附加优化）

### 问题

现在一个 agent 同时收到多条消息时，mailbus 一次性全部推送。agent 同时 ACK 所有消息，但实际只能一条一条执行——导致后面的任务被忽略或只做了完成回执的自动回复。

### 目标

同一个 agent 的消息串行派发：前一条 **acknowledged + done** 后才推送下一条。加急消息可以插队。

### 设计

#### 状态机约束

```
pending ──→ pushed ──→ acknowledged ──→ done
                          ↕ (等待中)    ← 下一条才能推
```

- 一个 agent 最多同时有 **1 条**消息是 `pushed` 状态
- 其余待推送的消息保持 `pending`，排队等待
- 当前消息变成 `done`（或 `failed/timeout`）后才把下一条标为 `pushed` 并推送

#### 改动点

**`lib/scanner.py` — `scan_all()` 或 `build_queues()` 修改：**

```python
def build_queues(data_dir, agents):
    urgent_queue = {}
    normal_queue = {}
    scanned = scan_all(data_dir, agents)

    for name, urgent_msgs, normal_msgs in scanned:
        # 检查该 agent 是否已有 pushed 消息
        inbox = load_inbox(data_dir, name)
        has_active = any(get_msg_state(m) == "pushed" for m in inbox.messages)
        if has_active:
            # 有正在推送中的消息，暂不推新的
            continue

        # 合并加急+普通，加急在前
        all_msgs = urgent_msgs + normal_msgs
        if not all_msgs:
            continue

        # 每次只推送第一条（加急优先）
        head = [all_msgs[0]]
        if all_msgs[0].priority == "urgent":
            urgent_queue[name] = head
        else:
            normal_queue[name] = head
        push_to_queue(data_dir, name, head, is_urgent=(all_msgs[0].priority == "urgent"))

    return urgent_queue, normal_queue
```

**`lib/pusher.py` — 推送完成后检查下一轮：**

推成功并标记 `acknowledged` → `done` 后，`scanner.py` 下一次 scan 会发现没有 active 消息，于是推排队中的下一条。

**msg_field `state` 的兼容：**

当前有些消息的 `state` 字段和 `status` 字段并存，需要统一。`get_msg_state()` 负责返回实际有效状态：

```python
def get_msg_state(m):
    """返回消息的实际有效状态（优先 state，fallback status）"""
    if isinstance(m, dict):
        return m.get("state", m.get("status", "pending"))
    return m.state or m.status or "pending"
```

#### 边界情况

| 情况 | 处理 |
|------|------|
| agent 从不写 ack（auto_ack=true） | 推送后直接标记 acknowledged→done，然后推下一条 |
| agent 超时未完成（3次催办后 timeout） | timeout 后视为 done（失败），推下一条 |
| 加急消息插队 | 检查到有 urgent 消息且当前 active 是普通消息时，先发加急 |
| agent 离线 | 消息保持 pending，等上线后再推 |

### 不需要改的

- 跨 agent 的并行扫描不变（不同 agent 之间仍然并行）
- `/api/send-msg` 即时推送不变（手动发的消息走独立路径）
- 消息存储格式不变
