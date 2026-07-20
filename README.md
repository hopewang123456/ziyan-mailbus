# mail — mailbus source & runtime

[中文说明](README.zh.md)

mailbus physical root = this repo (`MAILBUS_ROOT`). Set paths via env — **never commit machine absolute paths**.

| Path | Role |
|------|------|
| `store/` | `MAILBUS_DATA` — inbox, config.json, msg-results |
| `run/` | launch-queue, pid files |
| `lib/` · `tools/` · `migrate/` · `docker-agents/` | mailbus source (SoT) |
| `logs/` | historical logs |
| `skills/` · `rules/` · `plans/` · `docs/` | knowledge dirs; on local hosts often junctions → Vault |

## CLI

```bash
cd mail
pip install -e .
mailbus --help
```

Typical `.env` (in `mail/.env`, **do not commit**):

```bash
MAILBUS_ROOT=/path/to/mail
MAILBUS_DATA=/path/to/mail/store
HERMES_DATA=/path/to/hermes-data/.hermes
OPENCLAW_WORKSPACE=/path/to/openclaw_space
OPENCODE_ROOT=/path/to/opencode
LINGXIAO_WORKSPACE=/path/to/lingxiao
LINGJIAN_WORKSPACE=/path/to/lingjian
CODEX_SKILLS=/path/to/.codex/skills
NODE_MODULES=/path/to/node_modules
TEAM_PACK_ROOT=/path/to/team-pack
DEEPSEEK_API_KEY=your-api-key
```

Template: [`migrate/env.template`](migrate/env.template).

## Skills / Memory mount model

**Principle: Vault (or any external tree) is the SoT; runtime homes are mount points; the published repo must not hard-code host Vault absolute paths.**

### Local (optional Vault)

| Layer | Approach |
|-------|----------|
| Host | Junction/symlink `mail/skills\|rules\|plans\|docs`, per-agent `skills/`, and most `memories/` → your Vault tree |
| Docker base | [`docker-agents/docker-compose.yml`](docker-agents/docker-compose.yml) uses **repo-relative** `../…` plus `${ENV}` for external homes |
| Docker local | Machine/Vault absolute mounts only in **`docker-compose.override.yml` (gitignored)** |
| Template | Copy [`docker-agents/docker-compose.override.example.yml`](docker-agents/docker-compose.override.example.yml) → `override.yml` and replace `/path/to/…` |

Windows / WSL Docker often **cannot follow NTFS junctions**, so containers that need Vault SoT must bind-mount the real Vault path in `override.yml`.

Do **not** point committed `MAILBUS_*_ROOT` env at Vault (avoids dual-source with junctions). Local = junction + override.

### Publish / external consumers

1. See [`examples/config.example.json`](examples/config.example.json) → `profile_paths.skills_dirs` / `memory_dir`.
2. Leave empty / omit → each runtime uses its own default `skills/` and `memory/`; mailbus **does not inject** paths.
3. CI may set `MAILBUS_SKILLS_ROOT` etc. to in-repo demos ([`migrate/env.template`](migrate/env.template)).

### Per-agent external mounts

| Runtime / service | Container (or host) mount | External SoT / how to wire |
|-------------------|---------------------------|----------------------------|
| **mailbus** | `../skills` → `/mailbus/skills` (etc.) | Repo demo; override → Vault `skills/mailbus` |
| **Hermes** (`hermes`) | `${HERMES_DATA}` → `/home/hermes/.hermes`; profiles’ `skills` / `memories` | Set `HERMES_DATA`; optional Vault role views under profiles |
| **OpenClaw** (`openclaw`) | `${OPENCLAW_WORKSPACE}` → `/workspace`; `skills` · `memory` | Set `OPENCLAW_WORKSPACE`; override can pin Vault `library/openclaw` + agent memory |
| **Codex · 灵霄** (`lingxiao`) | `${LINGXIAO_WORKSPACE}` → `/workspace/lingxiao`; `${CODEX_SKILLS}` → `/home/node/.codex/skills` | Set workspace + `CODEX_SKILLS` (or Vault `02-agent-specific/codex` via override) |
| **Codex · 灵鉴** (`lingjian`) | `${LINGJIAN_WORKSPACE}` → `/workspace/lingjian`; same Codex skills mount | Same pattern as lingxiao |
| **OpenCode · 大力** (`dali`) | `${OPENCODE_ROOT}` → `/workspace/opencode` (+ `skills`) | Set `OPENCODE_ROOT`; override can pin Vault opencode skills |
| **Claude Code · 灵云/灵验** | Host ttyd (not Docker volumes); `~/.claude/skills` | Host install; optional Vault → `~/.claude/skills` junction |
| **AgentMemory** | `${NODE_MODULES}` → `/node_modules` | Set `NODE_MODULES` to a tree containing `@agentmemory/agentmemory` |
| **team-pack** (optional) | `${TEAM_PACK_ROOT}/skills\|rules` → `/team-pack/…` | Set `TEAM_PACK_ROOT` if you ship a sibling pack |

Role views that need mailbus protocol skills must include the **mailbus** stack; `_USE_FULL_LIBRARY` agents mount the full library (often via a `library/mailbus` junction).

### Quick start (Docker team)

```bash
cp migrate/env.template .env          # edit paths + API keys
cp docker-agents/docker-compose.override.example.yml \
   docker-agents/docker-compose.override.yml   # optional Vault binds
cd docker-agents && docker compose up -d
# or: bash docker-agents/start-team.sh
```

## Other docs

- Migration: [`docs/migration-guide.md`](docs/migration-guide.md)
- Chinese overview: [`README.zh.md`](README.zh.md)
