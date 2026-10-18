# Claude Code — 能力边界

## Pro 编码

- permission_mode: `acceptEdits`
- 跨文件 refactor、长工单、复杂测试+代码
- 与日常编码 agent 分工：日常 → 常规；pro → agent-h

## 测试

- permission_mode: `dontAsk`
- allowedTools: **Bash, Read, Glob, Grep** only
- pytest / Playwright / E2E，不写业务实现

## 不能做

- auto_ack
- Docker 内执行（宿主机 WSL/ttyd :9260/:9261）
- 手改 CLAUDE.md 作为持久配置

## 会话

- 每次 `-p` 独立 headless run
- 交互：`launch_agent.py {agent} browser`
