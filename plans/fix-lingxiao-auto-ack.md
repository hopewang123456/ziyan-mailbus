# 灵霄 (Cline) auto-ack 根治方案设计

> 问题：Cline hub-daemon 收到 mailbus CLI 推送后，自动返回"完成回执"但不执行任务。
> 涉及角色：灵霄（Cline CLI v3.0.15）
> 关联问题：大力（OpenCode）也有类似行为，方案可通用

---

## 方案一：两步推送 + 命令验证

### 流程

```
mailbus 推送第1步（验证命令）
  → 灵霄收到，执行命令（如 cat /path/to/file | head -5）
  → 灵霄回复 stdout
  → mailbus 验证 stdout 是否符合预期
  → 通过后，mailbus 推送第2步（实际任务）
```

### 第1步消息示例
```
📬 验证命令
请执行以下命令并将输出完整回复给我：
  cat /mnt/e/ai_tools/mail/store/msg-files/msg-xxx.md

如果回复了命令输出的内容，说明你在认真执行。
如果只回"完成回执"，说明你没有读消息。
```

### 验证逻辑
```python
def verify_command_reply(reply_text, expected_pattern=None):
    """检查回复是否包含命令执行的 stdout，而不是完成回执"""
    # 拒绝完成回执模板
    if "✅ 任务完成回执" in reply_text:
        return False, "收到完成回执，未执行命令"
    # 检查是否有实质内容（不是 AI SDK Warning 开头）
    if reply_text.startswith("AI SDK Warning"):
        return False, "只有 SDK 警告，无实质输出"
    # 有内容就通过
    if len(reply_text.strip()) > 20:
        return True, "验证通过"
    return False, "回复内容过短"
```

### 优点
- 命令的 stdout 无法伪造，auto-ack 机制无法绕过
- 对灵霄的改动为 0（mailbus 侧做验证）
- 已验证可行（2026-06-04 `sed + grep` 命令成功执行过）

### 缺点
- 多了一次往返，任务延迟 15-30 秒
- 部分简单任务（如"读文件"）不需要两步

---

## 方案二：文件通信模式（纯文件）

### 流程

```
mailbus 写任务文件到 store/msg-files/xxx.md
  → 推送灵霄："请读取 msg-files/xxx.md，执行后写结果到 msg-results/xxx.json"
  → 灵霄读文件 → 执行 → 写结果文件
  → mailbus 检测到结果文件存在 → 确认完成
```

### 任务文件格式
```markdown
# 任务: 审查代码
message_id: msg-xxx
from: lingzhao
type: review

## 任务内容
审查 /mnt/e/ai_tools/mail/docs/index.html 的第 100-200 行，
检查是否存在 XSS 漏洞。

## 完成要求
执行完毕后，将结果按以下格式写入 /mnt/e/ai_tools/mail/store/msg-results/msg-xxx.json：
{
  "conclusion": "pass|fail",
  "issues": [...],
  "summary": "..."
}
```

### 检测逻辑
```python
def check_result(task_id):
    """检查灵霄是否写入了结果文件"""
    result_file = f"{data_dir}/msg-results/{task_id}.json"
    if os.path.exists(result_file):
        with open(result_file) as f:
            return json.load(f)
    return None  # 还没完成
```

### 优点
- 完全绕过 auto-ack（Cline 的 ack 机制只对 CLI 推送有效，对文件操作无效）
- 任务内容不限长度
- 灵霄不需要实时在线，结果文件写好后 mailbus 下次 scan 就能检测到

### 缺点
- 需要改灵霄的推送模式（从 CLI message 改为文件指令）
- 灵霄需要知道写结果到哪个文件（在推送消息中指明）

---

## 方案三：混合模式（推荐）

结合方案一和方案二的优点：

| 任务复杂度 | 推送方式 | 说明 |
|-----------|---------|------|
| 简单命令（curl/echo/ls） | 方案一 | 直接推命令，验证 stdout |
| 中等任务（改代码/审查） | 方案二 | 推文件路径，灵霄读+写结果 |
| 复杂任务（多文件改动） | 方案二 | 推文件路径，灵霄读+写结果 |

### 消息体模板

```
📬 任务
来自: lingzhao
消息ID: msg-xxx

📄 任务文件: /mnt/e/ai_tools/mail/store/msg-files/msg-xxx.md
📄 结果写入: /mnt/e/ai_tools/mail/store/msg-results/msg-xxx.json

⚠️ 约束规则（必须遵守）：
1. 先写 ack 确认已读
2. 读取任务文件中的完整指令
3. 执行任务
4. 将执行结果写入结果文件（JSON格式，具体字段见任务文件）
5. 回复"已完成"并附上结果文件的路径

❌ 禁止：只回"完成回执"而不执行任务
❌ 禁止：不读取任务文件就直接回复
```

### mailbus 检测逻辑

```python
def check_task_completion(data_dir, agent_name, msg_id):
    """检查任务是否真正完成"""
    # 1. 检查结果文件是否存在
    result_file = f"{data_dir}/msg-results/{msg_id}.json"
    if os.path.exists(result_file):
        try:
            with open(result_file) as f:
                result = json.load(f)
            return True, result.get("conclusion", "done")
        except Exception:
            return False, None
    
    # 2. 检查回复中是否包含"完成回执"（auto-ack 的典型回复）
    inbox_file = f"{data_dir}/inbox/{agent_name}/inbox.json"
    inbox_data = json_read(inbox_file, {})
    for m in (inbox_data.get("messages") or []):
        if m.get("id") == msg_id and m.get("state") == "done":
            reply = (m.get("content") or "")
            if "✅ 任务完成回执" in reply:
                return False, "auto-ack（有完成回执无结果文件）"
    
    return False, None
```

---

## 实施计划

| 步 | 内容 | 工作量 |
|----|------|--------|
| 1 | 实现灵霄专用的 `task_file` 推送模板（替代普通消息推送） | 小 |
| 2 | 实现 `verify_command_reply()` 验证函数 | 小 |
| 3 | 实现 `check_task_completion()` 检测函数 | 小 |
| 4 | 修改灵霄的推送消息体，包含任务文件和结果文件路径 | 小 |
| 5 | 测试：推一个简单命令 + 推一个文件任务 | 中 |
| 6 | 上线后观察灵霄执行情况，迭代调整 | 持续 |

---

## 预期效果

| 状态 | 灵霄行为 | mailbus 反应 |
|------|---------|-------------|
| ❌ auto-ack | 回完成回执 | 检测到无结果文件，标记为未完成，重新推送 |
| ✅ 正常执行 | 读文件→写结果→回复 | 检测到结果文件，标记为完成，推进 chain |
| ⏳ 执行中 | 在读文件/写代码 | 未有结果文件，标记为 running，不催办 |

---

## 实施细节补充：报告模板适配

### 灵霄结果文件模板（lingxiao-report）

```json
{
  "template": "lingxiao-report",
  "conclusion": "done | blocked | failed",
  "summary": "一句话总结完成情况",
  "output": {
    "type": "file_changes | review_result | research_report",
    "files": ["改动的文件列表"],
    "diff_path": "store/diffs/msg-xxx.diff（可选）",
    "test_result": "pass | fail（可选）"
  },
  "next_role": "审查官 | 方案设计师 | ...",
  "cc": ["lingzhao"]
}
```

### mailbus 检测 + 推进逻辑

```python
def check_lingxiao_result(data_dir, agent_name, msg_id):
    result_file = f"{data_dir}/msg-results/{msg_id}.json"
    if not os.path.exists(result_file):
        return None  # 还没完成
    
    with open(result_file) as f:
        result = json.load(f)
    
    # 验证结论
    if result.get("conclusion") != "done":
        return {"status": "failed", "reason": result.get("summary", "")}
    
    # 读取 next_role 自动推进
    next_role = result.get("next_role")
    output = result.get("output", {})
    
    return {
        "status": "done",
        "next_role": next_role,
        "output": output,
        "summary": result.get("summary", "")
    }
```

### 灵鉴审查任务构建（从灵霄结果自动生成）

从灵霄的结果文件中读取产出信息，构建审查消息：

```
📬 审查任务
来自: 灵霄 (开发工程师)

灵霄的产出:
  改动文件: docs/index.html
  diff: /mnt/e/ai_tools/mail/store/diffs/msg-xxx.diff（如存在）
  自测结果: pass

请审查以上改动，完成后写审查结论到:
  /mnt/e/ai_tools/mail/store/msg-results/msg-xxx-review.json
```
