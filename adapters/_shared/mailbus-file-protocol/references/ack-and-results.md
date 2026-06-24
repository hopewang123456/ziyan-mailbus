# ack 与 msg-results 参考（L0）

交付 SoT **按框架** → L1 `framework-runtime-*/references/delivery.md`（不在此重复框架表）。

## ack

路径：`store/inbox/{agent}/ack.json`

```json
{"action": "ack", "msg_id": "<id>", "agent": "<agent_id>", "timestamp": "<ISO8601>"}
```

收到 mailbus push 后**第一时间**写入。

## msg-results 通用 schema

用于 codex / claude_code / cline 等框架（L1 mandatory）。

路径：`store/msg-results/{msg_id}.json`

- **无此文件 = 未完成**（适用框架见 L1 delivery.md）
- `summary` ≤200 字；细节放 `details` 或独立 md
- `status: failed` 时写 `reason`

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

## opencode / openclaw / hermes

见对应 L1：
- opencode → `mail/adapters/opencode/framework-runtime/references/delivery.md`
- openclaw → `mail/adapters/openclaw/framework-runtime/references/delivery.md`
- hermes_profile → `mail/adapters/hermes_profile/framework-runtime/references/delivery.md`

## 路径契约

- mailbus store：`/mailbus/store`（宿主机 `mail/store`）
- inbox：`store/inbox/{agent}/`
- msg-files：`store/msg-files/`
