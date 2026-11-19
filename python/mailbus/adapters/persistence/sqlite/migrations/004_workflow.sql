-- 004 流程上下文：定义、不可变版本、任务与任务节点。
-- 任务持有 workflow_version，发布新版本不会改变运行中任务。

CREATE TABLE IF NOT EXISTS wf_defs (
    workflow_id       TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    latest_version    INTEGER NOT NULL DEFAULT 0,
    published_version INTEGER,
    created_at        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS wf_versions (
    workflow_id  TEXT NOT NULL,
    version      INTEGER NOT NULL,
    state        TEXT NOT NULL,
    nodes        TEXT NOT NULL DEFAULT '[]',
    created_at   REAL NOT NULL,
    published_at REAL,
    PRIMARY KEY (workflow_id, version)
);

CREATE TABLE IF NOT EXISTS task_tasks (
    task_id          TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    state            TEXT NOT NULL,
    workflow_id      TEXT,
    workflow_version INTEGER,
    owner_id         TEXT,
    created_by       TEXT,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_tasks_state
    ON task_tasks (state, created_at);

CREATE INDEX IF NOT EXISTS idx_task_tasks_owner
    ON task_tasks (owner_id, state);

CREATE TABLE IF NOT EXISTS task_nodes (
    task_id    TEXT NOT NULL REFERENCES task_tasks (task_id) ON DELETE CASCADE,
    node_id    TEXT NOT NULL,
    name       TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    state      TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (task_id, node_id)
);
