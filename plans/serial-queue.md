# 串行队列 + 并发控制方案

> 同一个 agent 的任务串行执行或在并发上限内排队。
> 不管任务是谁发的，统一由 mailbus 队列管理。

---

## 现状

mailbus 一次性把多条消息推给同一个人。agent 无法同时处理，导致：
1. 后面的消息被忽略或只 auto-ack
2. 任务淹没了看不到该做什么

---

## 方案

### 每个 agent 配置并发上限

在 `config.json` 的 agent 配置中新增 `max_concurrency`：

```json
{
  "agents": {
    "lingzhao":  { "type": "hermes", "max_concurrency": 1 },
    "lingjin":   { "type": "hermes_profile", "max_concurrency": 1 },
    "lingxi":    { "type": "hermes_profile", "max_concurrency": 1 },
    "lingjian":  { "type": "hermes_profile", "max_concurrency": 2 },
    "lingyan":   { "type": "hermes_profile", "max_concurrency": 2 },
    "lingxun":   { "type": "hermes_profile", "max_concurrency": 1 },
    "lingxiao":  { "type": "cline", "max_concurrency": 1 },
    "dali":      { "type": "opencode", "max_concurrency": 3 },
    "xiaoqi":    { "type": "openclaw", "max_concurrency": 1 },
    "yige":      { "type": "openclaw", "max_concurrency": 1 }
  }
}
```

| 框架 | 默认并发 | 原因 |
|------|---------|------|
| Hermes chat -q | 2 | 每次独立进程，可并行 |
| Cline | 1 | 常驻 hub-daemon，一次处理一个 |
| OpenClaw | 1 | gateway 模式，消息排队 |
| OpenCode | 3 | 每次独立进程，可并行 |

### 检测逻辑

```python
def can_push_to_agent(data_dir, agent_name, max_concurrency):
    """检查该 agent 当前是否有空接收新消息"""
    if max_concurrency == 0:
        return True  # 不限
    
    inbox = load_inbox(data_dir, agent_name)
    active_count = sum(
        1 for m in inbox.messages
        if get_msg_state(m) in ("pushed", "running", "processing")
    )
    
    return active_count < max_concurrency
```

### build_queues 修改

```python
def build_queues(data_dir, agents):
    urgent_queue = {}
    normal_queue = {}
    scanned = scan_all(data_dir, agents)

    for name, urgent_msgs, normal_msgs in scanned:
        cfg = agents.get(name, {})
        max_con = cfg.get("max_concurrency", 1)
        
        # 并发满了 → 暂不推新的
        if not can_push_to_agent(data_dir, name, max_con):
            continue
        
        # 合并加急+普通，加急优先
        all_msgs = urgent_msgs + normal_msgs
        if not all_msgs:
            continue
        
        # 取到并发上限（通常只推1条，但支持并行框架可以多推）
        available = max_con - active_count(data_dir, name)
        to_push = all_msgs[:available]
        
        for msg in to_push:
            is_urgent = msg.priority == "urgent"
            if is_urgent:
                urgent_queue.setdefault(name, []).append(msg)
            else:
                normal_queue.setdefault(name, []).append(msg)
        
        push_to_queue(data_dir, name, to_push, 
                      is_urgent=(to_push[0].priority == "urgent"))

    return urgent_queue, normal_queue
```

### 效果

```
大力（max=3）：
  并发满 → 新任务排队 → 有人完成 → 自动推下一个

灵霄（max=1）：
  有任务在执行 → 新任务排队 → 当前完成后 → 自动推下一个
  永不分身，永不淹没
```

### 需要改的模块

| 文件 | 改动 |
|------|------|
| `lib/scanner.py` | `build_queues()` 加并发检测 |
| `lib/scanner.py` | 加 `can_push_to_agent()` 和 `active_count()` 辅助函数 |
| `store/config.json` | 各 agent 加 `max_concurrency` 字段 |
