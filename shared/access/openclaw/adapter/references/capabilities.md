# OpenClaw — 能力边界

## 能做

- Gateway 调度、Kanban、验收、curl mailbus API
- workspace skills（dev-coding-agent、ui-ux 等）
- 本地 `openclaw agent` / `tui`

## 不能做

- 大块编码（派编码 agent）
- 混淆多 openclaw state_dir（会话污染）
- 在群聊里代主人发声（AGENTS.md Red Lines）

## state_dir

| agent | OPENCLAW_STATE_DIR |
|-------|-------------------|
| agent-c | `/workspace/data/.openclaw-agent-c` |
| agent-g | `/workspace/data/.openclaw-agent-g` |

## 会话

- mailbus push 触发 `--message` 一轮
- TUI session 可延续（interactive launch）
