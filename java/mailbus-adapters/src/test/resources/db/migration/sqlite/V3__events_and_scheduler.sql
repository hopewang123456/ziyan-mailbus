-- V3: lifecycle event stream (AgentScope typed-events borrowing, plan §4)
-- and scheduler heartbeat. Every FSM transition appends one immutable row;
-- trace reads this table instead of reconstructing from snapshots.

CREATE TABLE msg_events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id      TEXT NOT NULL,
    agent       TEXT NOT NULL,
    kind        TEXT NOT NULL,             -- created | pushed | state | archived | patrol_stale
    state_from  TEXT,
    state_to    TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL              -- ISO-8601 UTC
);

CREATE INDEX idx_events_msg ON msg_events (msg_id, seq);

CREATE TABLE scheduler_state (
    id          INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
    job         TEXT NOT NULL,
    last_run_at TEXT NOT NULL,
    last_ok     INTEGER NOT NULL DEFAULT 1,
    last_error  TEXT NOT NULL DEFAULT ''
);
