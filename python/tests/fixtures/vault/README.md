# Test vault fixtures

Minimal stubs so drill / registry tests do not skip on missing Vault or external-tools assets.

| Path | Purpose |
|------|---------|
| `identities/example-agent.md` | MdAgentsConfig identity seed |
| `external-tools/registry.json` | `webhook-multi-publish` tool for drill |
| `external-tools/grants.json` | Grants `mailbus` → publish tool |

Use `tests.test_helpers.seed_runtime_from_sot` for full store layout; point
`MAILBUS_EXTERNAL_TOOLS_DIR` at `external-tools/` when exercising drills.
