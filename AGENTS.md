# AGENTS.md — Mailbus entry for coding agents

## Product

**mailbus**: file-based Agent-to-Agent message bus. Framework-agnostic (Hermes, OpenClaw, Codex, Claude Code, …).

## Repo roots

| Path | Role |
|------|------|
| `lib/` | Application code (Ports & Adapters) |
| `lib/composition.py` | **Only** Composition Root |
| `bus/` | CLI / serve entry (`python -m bus`) |
| `web/` | Cockpit (React) |
| `config/` | Seed / template config |
| `store/` | Runtime data (local, gitignored secrets) |
| `docker-agents/` | Compose stacks |
| `docs/` | In-repo docs |
| `tests/` | pytest |

## Architecture SoT

- 代码分层/快速开始：本文件上方 [`ARCHITECTURE.md`](ARCHITECTURE.md)
- 完整架构文档：Obsidian `Agent/01-mailbus/016-docs/0161-architecture/`（SoT）
- Vault 计划：`Agent/01-mailbus/017-plans/`（Obsidian）
- 路径/结构映射：`Agent/_path-map.json`（机器可读）

## Dependency rule (target)

```
tools/ · lib/api/  →  lib/application/  →  lib/interfaces/  ←  lib/adapters/
                              ↓
                         lib/domain/ · lib/core/
                              ↓
                         lib/infra/
```

- `application` must not import concrete `adapters.frameworks.*`
- `adapters` must not import `application`
- `domain` must not import upper layers

## How to work

1. Read `ARCHITECTURE.md` + relevant package `Overview.md`
2. Prefer DeepSeek for routine edits; use stronger models for cross-package moves
3. Run a **targeted** pytest after changes; full suite for gate waves
4. Never commit `.env` / secrets / personal agent rosters

## Quick commands

```bash
pip install -e .
mailbus init --data-dir ./store
mailbus serve --host 0.0.0.0 --port 9814 --data-dir ./store
pytest tests/test_import_layers.py -q
```
