-- V4: agent cards (M3) — minimal merge of the python instance-card /
-- role-card split: runtime identity + adapter wiring. adapter_config holds
-- the declarative push argv (JSON), never a shell string.

CREATE TABLE agent_cards (
    id              TEXT PRIMARY KEY,          -- agent id (e.g. agent-demo, lingyan)
    type            TEXT NOT NULL,             -- framework: claude_code | codex | hermes | cli | none ...
    run_target      TEXT NOT NULL DEFAULT 'windows',  -- windows | wsl | linux | docker
    enabled         INTEGER NOT NULL DEFAULT 1,
    adapter_config  TEXT NOT NULL DEFAULT '{}',-- {"push_argv": ["claude","-p","{MSG}"], "timeout_s": 300}
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX idx_cards_type ON agent_cards (type, enabled);
