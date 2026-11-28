# hermes_profile delivery

Hermes Profile 交付规则（默认规则示例）。

## 回传
- 任务完成后通过 A2A `result` 回传状态，使用 `completed`、`failed`、`needs_info` 或 `needs_human`。
- 回传应包含任务标识与必要输出；失败时必须说明原因。
- 产物通过 artifact 引用交付，不在消息中伪造本地产物路径。

## 执行纪律
- 未实际完成不得回传 `completed`。
- 重复结果不得覆盖已确认的最终状态。
- 长任务保持心跳；无法继续时及时报告，而不是静默等待。

## 上下文
- 只使用任务所需的上下文与凭据。
- 不在结果中泄露密钥、内部 token 或无关隐私数据。
