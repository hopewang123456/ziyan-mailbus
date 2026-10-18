# Hermes — 能力边界

## 能做

- 方案设计、文档、调研、审计类文字工作
- 读写在 `/mailbus/store` 及 HERMES_HOME 下文件
- `hermes chat` 交互（dashboard 端口 9120–9127）
- 调用 team memory（memory.py / shared-memory）

## 不能做 / 慎做

- 替代 OpenCode/Codex 的大块编码（应派编码 agent）
- 假设 push 后会自动续 session（每 push 独立 `-q`）
- 修改 mailbus Core / adapter 代码（除非工单明确）
- 绕过 human gate 的自动化（见 ADR-008）

## 会话模型

- **有状态**：Hermes profile / dashboard 会话可延续
- **mailbus push**：每次 `-q` 独立，push 正文是唯一任务入口

## cwd

- Docker：`/mailbus/store` 挂载
- 身份：`/mailbus/identities/` 只读
