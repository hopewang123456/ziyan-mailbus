# Agent 框架 Runtime Skill 库（L0 + L1）

> **L2 工种** → [`../roles/README.md`](../roles/README.md)  
> **分层模型** → [`../docs/agent-layer-spec.md`](../docs/agent-layer-spec.md)

每个 agent 除 L3 领域 skill 外，sync 自动注入 **L0–L2** layer skills。

## L0 共享

| 目录 | skill id |
|------|----------|
| [`_shared/agent-universal/`](_shared/agent-universal/) | `agent-universal` |
| [`_shared/mailbus-file-protocol/`](_shared/mailbus-file-protocol/) | `mailbus-file-protocol` |

## L1 框架

| `config.json` type | 目录 | Sync 脚本 |
|--------------------|------|-----------|
| `hermes_profile` | [`hermes_profile/`](hermes_profile/) | `sync-hermes-framework-skill.sh` |
| `opencode` | [`opencode/`](opencode/) | `sync-opencode-framework-skill.sh` |
| `codex` | [`codex/`](codex/) | `sync_codex_agent_skills.py` |
| `claude_code` | [`claude_code/`](claude_code/) | `sync-claude-agent-context.py` |
| `openclaw` | [`openclaw/`](openclaw/) | `sync-openclaw-framework-skill.sh` |
| `hermes` | [`hermes/`](hermes/) | legacy |
| `cline` | [`cline/`](cline/) | deprecated |
| `cursor` | [`cursor/`](cursor/) | stub |

## 索引与注入

- SoT：`store/agents/json/skills-index.json`
- 补全：`python tools/patch-skills-index-framework.py`
- 校验：`python tools/validate-agent-layers.py --check`

## 设计原则

- 主 `SKILL.md` ≤120 行；细节 `references/` 按需 Read
- **交付 SoT 仅定义在 L1** `references/delivery.md`
- identity / AGENTS.md **不** inline mailbus 规则
