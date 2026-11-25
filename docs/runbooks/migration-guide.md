# Migration guide (Ports & Adapters deep cleanup)

> **历史文档（2026-11-25 标注）**：本文记录 2026-08 的 `lib/` 包重命名，与当前 SQLite 迁移无关。当前迁移基线见 [design/migration-review.md](../design/migration-review.md)。

This document summarizes the package rename/move from the pre-cleanup layout to the current tree.

## Package map

| Old path | New path |
|----------|----------|
| `lib/ports/` | `lib/interfaces/` |
| `lib/transport/` (A2A) | `lib/core/a2a/` |
| `lib/agent_adapters.py` | `lib/adapters/frameworks/` + `lib/application/push/` |
| `lib/scanner.py` | `lib/application/scan/` |
| `lib/access_adapters.py` | `lib/adapters/config/access_adapters.py` |

## Dependency rule

See [ARCHITECTURE.md](../ARCHITECTURE.md):

```
tools/ · lib/api/ → lib/application/ → lib/interfaces/ ← lib/adapters/
                         ↓
               lib/domain/ · lib/core/
                         ↓
                    lib/infra/
```

## Config & store

- Seeds live under `config/`; runtime reads `store/config.json` (from `mailbus init`).
- `mailbus_automation.legacy_result_read` defaults to **false** in `config/mailbus/base.json`.
- Agent identities may come from Vault MD (`MAILBUS_IDENTITIES_ROOT`) or JSON overrides.

## Tests

- Import layer gate: `pytest tests/test_import_layers.py -q`
- Acceptance subset: `pytest tests/test_acceptance_v_suite.py -q`

## Vault / plans SoT

Obsidian plans under `Projects/mailbus/plans/` — current deep-cleanup SoT:
`2026-08-10-arch-deep-cleanup.md`.

Cursor plan `mailbus-arch-deep-cleanup` is execution tracker; do not edit while running waves.
