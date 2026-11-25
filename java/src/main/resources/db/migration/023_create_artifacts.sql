-- 023 节点产物与修改记录。
CREATE TABLE IF NOT EXISTS task_node_artifacts (
    artifact_id   TEXT PRIMARY KEY,
    task_id       TEXT NOT NULL,
    node_id       TEXT NOT NULL,
    run_id        TEXT NOT NULL,
    file_path     TEXT NOT NULL,
    file_name     TEXT NOT NULL,
    artifact_type TEXT,
    description   TEXT,
    created_by    TEXT NOT NULL,
    created_at    REAL NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_artifacts_task ON task_node_artifacts (task_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON task_node_artifacts (run_id);

CREATE TABLE IF NOT EXISTS task_node_artifact_edits (
    edit_id      TEXT PRIMARY KEY,
    artifact_id  TEXT NOT NULL,
    edited_by    TEXT NOT NULL,
    edited_at    REAL NOT NULL,
    version      INTEGER NOT NULL,
    diff_summary TEXT,
    FOREIGN KEY (artifact_id) REFERENCES task_node_artifacts (artifact_id)
);

CREATE INDEX IF NOT EXISTS idx_artifact_edits_artifact
    ON task_node_artifact_edits (artifact_id);
