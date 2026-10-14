# tests/

pytest suite for mailbus.

## Conventions

- Prefer plain `def test_*` pytest style for new tests.
- Existing `unittest.TestCase` modules remain valid; convert opportunistically.
- Layer guard: `test_import_layers.py` must stay green after package moves.
- Legacy wave/phase prefixes in filenames (`test_phase*`, `test_wave*`) are historical labels; acceptance suite methods no longer use `test_vN_` prefixes.

## Fixtures

- `tests/fixtures/vault/` — fake identities / external-tools for skips→pass
- `tests/harness_fixtures/` — record / replay / stub (ex-`lib/harness`)
- Local `skills/` is gitignored; stubs may be generated for layout tests
