# Codex — 能力边界

## 能做

- `workspace-write` sandbox 内改代码、跑 shell
- 架构文档、ADR、PR 审查、安全扫描类任务
- 读 `.codex/skills` 同步的角色 skill

## 不能做

- auto_ack
- lingyan 式受限只读 E2E（用 claude_code dontAsk）
- 假设下一条 push 记得本轮结论（必须落盘 msg-results）

## 容器

- lingxiao / lingjian 独立 codex-agent 容器
- `CODEX_AGENT` 环境变量标识 agent

## 与 Claude Code 分工

| 场景 | Agent |
|------|-------|
| 架构/ADR | lingxiao Codex |
| pro 跨文件 refactor | lingyun Claude |
| 代码审查 | lingjian Codex |
