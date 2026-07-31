# Mailbus `config/` — layout & clone setup

Unified app config seeds live here. **Runtime always reads files without `.example`
in the name** (e.g. `launch-ports.json`). Files named `*.example.json` are templates
for you to copy after `git clone`.

## Clone setup (sensitive / personal Agent)

1. Copy each needed `*.example.json` beside it.
2. Rename by **removing** `.example` from the filename (`foo.example.json` → `foo.json`).
3. Edit the new file: your API keys, paths, and **your own agent ids** (not someone else’s roster).

Optional helper (does not overwrite existing files):

```bash
python -c "from lib.config_files import materialize_from_example; from pathlib import Path; \
p=Path('config/mailbus/launch-ports.json'); materialize_from_example(p); print(p)"
```

## Sensitive / personal (example committed; real file gitignored)

| Local (do not commit) | Example (committed) |
|-----------------------|---------------------|
| `config/agents/<id>.override.json` | `config/agents/agent.override.example.json`, `coder.override.example.json`, `chat.override.example.json` |
| `config/mailbus/launch-ports.json` | `config/mailbus/launch-ports.example.json` |
| `access/transport/<id>/transport.json` | `examples/transport/agent-a|agent-coder|agent-chat/` |
| `access/external-tools/registry.json` | `access/external-tools/registry.example.json` |
| `access/external-tools/grants.json` | `access/external-tools/grants.example.json` |
| `.env`, `store/secrets.json` | `migrate/env.template`, `config/env.template`, `docker-agents/.env.example` |

### Your own Agents (e.g. replace 大力 / 小七)

1. Copy `examples/transport/agent-coder/transport.json` → `access/transport/<your-id>/transport.json` and edit paths.
2. Copy `config/agents/coder.override.example.json` → `config/agents/<your-id>.override.json`.
3. Copy `launch-ports.example.json` → `launch-ports.json` and map **your** ids to ports.
4. Register agents in `store/config.json` (see `examples/config.example.json`) and enable in the cockpit.

## Non-sensitive (committed as-is, no example required)

- `config/mailbus/base.json`, `agent-types.json`, `agent-channels.json`, `mailbus.json`
- `config/pipeline/*`, `scheduler/jobs.json`, `intake/bridge.json`, `dispatch/*`
- `config/frameworks/**`, `config/llm/ollama.json`, `config/services/*` (no live keys)
- `config/workflows/*`, `*.template.json`, `*.schema.json`

## Runtime rule

Loaders must open **`foo.json`**, never treat `foo.example.json` as the bound production config.
If the real file is missing, copy the example first.

---

# 中文摘要

- 案例文件名 = 实文件名多一段 `.example`；Git 只交 example；本机只用无 `.example` 的文件。
- Clone 后：复制 → 去掉 `.example` → 填自己的密钥与 **自己的 Agent id**。
- 个人名册（大力/小七等）不进仓库；用 `agent-coder` / `agent-chat` 等通用 example 起步。
- 无敏感的公共 JSON 可直接提交，不必强行拆 example。
- **代码只读不带 example 的实文件。**
