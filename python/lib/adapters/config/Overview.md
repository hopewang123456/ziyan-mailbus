# lib.adapters.config

Config file repos, token store, access adapter specs.

## Role

Implement `ConfigRepository` and auth/token persistence helpers.

## Dependency direction

`interfaces` ← this package → store files / `domain`

## Forbidden imports

`lib.application.*`

## Files

| File | Purpose |
|------|---------|
| `file_repo.py` | File config repository |
| `token_store.py` | Token persistence |
| `access_adapters.py` | Access adapter specs |
| `native_sync.py` | Native config sync |
| `native_scan.py` | Agent 安装路径资产扫描（35f）— 按 framework 扫 rule/skill/memory/identity + 三端路径 |
| `md_config.py` | Vault 身份区 YAML frontmatter（018-identities/<id>/：SOUL/IDENTITY/CLAUDE.md） |
| `composite_config.py` | MD agents + JSON fallback |

