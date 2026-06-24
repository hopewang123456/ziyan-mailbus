# Claude Code Adapter

> 状态：已实现  
> 更新：2026-06-24

mailbus 通过 `ClaudeCodeAdapter`（`type: claude_code`）将任务 push 到宿主机 Claude Code CLI，与 Codex（Docker）并行。

## 交付链双 Agent

| Agent | 角色 | permission_mode | 用途 |
|-------|------|-----------------|------|
| **lingyun** 灵云 | pro 精细编码 | `acceptEdits` | 跨文件 refactor、长工单 |
| **lingyan** 灵验 | 测试验证 | `dontAsk` + Bash/Read/Glob/Grep | pytest/Playwright/E2E，不写业务代码 |

两者共用 `mailbus_claude` 与 Claude 二进制，通过 **不同 inbox** + `max_concurrency: 1` 串行调度。

## 与 Codex / Cline 对比

| 维度 | Codex | Cline (legacy) | Claude Code |
|------|-------|----------------|-------------|
| 执行环境 | Docker `codex exec` | Docker / WSL | 宿主机 `claude -p` |
| 平台配置 | `mailbus_codex` | — | `mailbus_claude` |
| 完成 SoT | `msg-results` | `msg-results` | `msg-results` |
| auto_ack | 否 | 否 | 否 |

## 配置

### 全局：`mailbus_claude`

见 [`examples/config.example.json`](../examples/config.example.json) 与 `store/config.json`。

### Agent 示例

**灵云（编码）**

```json
{
  "lingyun": {
    "name": "灵云",
    "type": "claude_code",
    "models": ["minimax-m2"],
    "max_concurrency": 1,
    "claude": { "permission_mode": "acceptEdits" },
    "push": { "cwd": "E:\\ai_tools" },
    "launch": { "template": "claude_host" }
  }
}
```

**灵验（测试）**

```json
{
  "lingyan": {
    "name": "灵验",
    "type": "claude_code",
    "models": ["minimax-m2"],
    "max_concurrency": 1,
    "claude": {
      "permission_mode": "dontAsk",
      "push_flags": "--allowedTools \"Bash,Read,Glob,Grep\""
    },
    "push": { "cwd": "E:\\ai_tools" },
    "launch": { "template": "claude_host" }
  }
}
```

## Push 命令形态

- 灵云：`claude -p 'MSG' --permission-mode acceptEdits ...`
- 灵验：`claude -p 'MSG' --permission-mode dontAsk --allowedTools "Bash,Read,Glob,Grep" ...`

## 任务路由（派单参考）

| 场景 | Agent | 平台 |
|------|-------|------|
| flash 日常编码 | dali | OpenCode |
| pro / 长工单 | lingyun | Claude Code |
| 架构 / ADR | lingxiao | Codex flash |
| 代码审查 | lingjian | Codex reasoner |
| E2E / 回归测试 | lingyan | Claude Code |

## 文件协议

| 路径 | 用途 |
|------|------|
| `store/msg-files/{msg_id}.md` | 长任务工单 |
| `store/msg-results/{msg_id}.json` | **完成 SoT** |
| `store/inbox/{agent}/ack.json` | ack |

## Launch 前置

启动 browser/cli 前会自动：

1. `ensure_claude_agent_settings` — 从主 `~/.claude/settings.json` 复制 MiniMax 路由到 `.claude-<agent>/settings.json`
2. `sync-claude-agent-context` — 同步人设、`CLAUDE.md`、skills

**若仍连到 api.anthropic.com**：检查主目录 `C:\Users\<you>\.claude\settings.json` 是否含 `ANTHROPIC_BASE_URL`（MiniMax 网关）。

## Launch

**勿用 Claude Desktop**（底层 MiniMax/DeepSeek 路由）。看板 **Web** 按钮 → WSL **ttyd** 交互终端（`:9260` 灵云 / `:9261` 灵验）。

启动前会运行 `tools/sync-claude-agent-context.py` 同步 **各 agent 独立** 的 `CLAUDE.md`、`.claude-<agent>` 配置目录、skills 与 `{agent}-memory/output.md`。

| Agent | ttyd 端口 | 配置目录（默认） | permission |
|-------|-----------|------------------|------------|
| lingyun 灵云 | 9260 | `~/.claude-lingyun` | acceptEdits |
| lingyan 灵验 | 9261 | `~/.claude-lingyan` | dontAsk + Bash/Read/Glob/Grep |

```bash
./launch-agent.sh lingyun browser
./launch-agent.sh lingyan browser
python tools/launch-claude-browser.py lingyun --data-dir store
./launch-agent.sh lingyun cli
./launch-agent.sh lingyan cli
```

| 模式 | 说明 |
|------|------|
| `browser` | ttyd Web UI（DeepSeek 友好） |
| `cli` | WSL 弹窗交互 `claude` |
| `desktop` | **已禁用**（原生 Desktop 不支持当前模型路由） |

## 冒烟

```bash
cd mail
python tools/resolve-agent-cli.py lingyun --mode push --data-dir store
python tools/resolve-agent-cli.py lingyan --mode push --data-dir store
python -m bus send lingyan --type task --content "跑 smoke 测试并写 msg-results"
```
