# mailbus 核心协议（L0）

框架无关部分。交付 SoT **不在此定义** → 各 L1 `references/delivery.md`。

## ack

路径：`store/inbox/{agent}/ack.json`

```json
{"action": "ack", "msg_id": "<id>", "agent": "<agent_id>", "timestamp": "<ISO8601>"}
```

收到 push 后**第一时间**写入。只回复文字不算已读。

## msg-files

路径：`store/msg-files/{msg_id}.md`

- 存在则**完整阅读**后再执行
- 工单内 SPARC 阶段、文件路径、验收标准以此为准

## 禁止 phantom 完成

- 空泛「已完成」「应该好了」无效
- 必须满足 L1 交付 SoT（msg-results / patch+replies / 实质回复等）

## msg-results 通用 schema（参考）

部分框架（codex、claude_code）mandatory；opencode 见 L1 delivery。

```json
{
  "agent": "<agent_id>",
  "msg_id": "<msg_id>",
  "status": "done|failed",
  "summary": "≤200字",
  "checklist": ["约束1✓"],
  "timestamp": "<ISO8601>"
}
```

## 推送侧 token（agent 接收）

- CLI 正文 ≤600 字；长文已在 msg-files / tasks
- 先 memory search，再动手
- Skill references **按需 Read**

详细 → [`mailbus-file-protocol/references/push-discipline.md`](../../mailbus-file-protocol/references/push-discipline.md)
