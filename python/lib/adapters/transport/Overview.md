# lib.adapters.transport

MessageTransportPort adapters: file_bus, http_a2a, webhook, selecting router, CLI bridge.

## Role

Concrete outbound delivery channels for Mailbus.

## Envelope contract（A2A 与 file_bus 同构）

同一工单在团队内流转时，语义信封字段一致，**通道只决定入站形态，不改变语义**：

- 最小字段：`work_id`（task_id）、`from`（initiator）、`to`（to_agent）、`hop_id`（step_id）、`intent` / `payload`
- `transport`（a2a | file_bus）为**内部印章**，只进 Mailbus 内部与诊所审计（`step.transport_used`），不暴露给业务 Agent，Agent 不得据此改投递策略
- **每 hop 一章**：同一 hop 只走一种通道；A2A 优先，仅「未成功投递」时才托底 file_bus 并改章，禁止双写
- 选路只看**接收方**配置（`channels.a2a.enabled/available`、endpoint），不按发送方能力或整张工单绑死
- 无 A2A 的 Agent 纯 file_bus 仍可独立闭环

## Dependency direction

`interfaces.message_transport` ← this package → `domain`, `core.a2a` (http path), `application.harness` (file_bus wait)

## Forbidden imports

Prefer not importing other adapter families except `results` / shared utils.

## Files

| File | Purpose |
|------|---------|
| `file_bus.py` | Inbox write (+ optional harness wait) |
| `http_a2a.py` | A2A SendMessage wrapper |
| `webhook.py` | HTTP webhook POST |
| `router.py` | Channel selection（按接收方 + `channels.a2a.available`） |
| `a2a_probe.py` | 保存 Agent 时探测 A2A endpoint，写回 `channels.a2a.available` |
| `codes.py` | Exception → domain error |
| `bridge/` | `BridgedAgentPort` CLI + lifecycle rules |
