-- V1 init (sqlite dialect) — metadata schema per architecture plan §5.
-- Message bodies live in FILES (files-as-source-of-truth); this DB indexes
-- and tracks lifecycle state only. MySQL dialect twin lands in
-- db/migration/mysql/ when the mysql profile first ships.

CREATE TABLE msg_index (
    id          TEXT PRIMARY KEY,          -- msg-<uuid8>
    to_agent    TEXT NOT NULL,
    from_agent  TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'notice',
    priority    TEXT NOT NULL DEFAULT 'NORMAL',
    state       TEXT NOT NULL DEFAULT 'PENDING',
    file_path   TEXT NOT NULL,             -- relative path of the message file
    created_at  TEXT NOT NULL,             -- ISO-8601 UTC
    updated_at  TEXT NOT NULL
);

CREATE INDEX idx_msg_agent_state ON msg_index (to_agent, state);
CREATE INDEX idx_msg_created     ON msg_index (created_at);

-- Graph edges (plan §5.3): forward chains, task step DAG, collaboration matrix.
-- Traversal via WITH RECURSIVE (GraphQueries, M1+); loop cap = 8 hops.
CREATE TABLE edges (
    src         TEXT NOT NULL,
    dst         TEXT NOT NULL,
    kind        TEXT NOT NULL,             -- forward | task_step | collaboration
    created_at  TEXT NOT NULL,
    PRIMARY KEY (src, dst, kind)
);

CREATE INDEX idx_edges_kind_src ON edges (kind, src);
