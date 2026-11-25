-- 021 节点执行实例表 + 旧 task_nodes 回填。
CREATE TABLE IF NOT EXISTS task_node_runs (
    run_id               TEXT PRIMARY KEY,
    task_id              TEXT NOT NULL,
    node_id              TEXT NOT NULL,
    attempt_no           INTEGER NOT NULL,
    assigned_employee_id TEXT,
    role_id              TEXT,
    state                TEXT NOT NULL,
    fanout_group         TEXT,
    short_fanout         INTEGER NOT NULL DEFAULT 0,
    result               TEXT,
    parent_run_id        TEXT,
    dispatched_at        REAL,
    started_at           REAL,
    completed_at         REAL,
    deadline_at          REAL,
    escalated_at         REAL,
    UNIQUE (task_id, node_id, attempt_no)
);

CREATE INDEX IF NOT EXISTS idx_task_node_runs_task
    ON task_node_runs (task_id, node_id);
CREATE INDEX IF NOT EXISTS idx_task_node_runs_employee
    ON task_node_runs (assigned_employee_id, state);
CREATE INDEX IF NOT EXISTS idx_task_node_runs_deadline
    ON task_node_runs (state, deadline_at);

ALTER TABLE task_nodes ADD COLUMN current_run_id TEXT;

INSERT INTO task_node_runs (
    run_id, task_id, node_id, attempt_no, assigned_employee_id,
    state, dispatched_at, started_at, completed_at
)
SELECT 'run_legacy_' || n.task_id || '_' || n.node_id,
       n.task_id, n.node_id, 1,
       CASE WHEN n.state IN ('running', 'dispatched', 'blocked') THEN t.owner_id ELSE NULL END,
       CASE n.state
           WHEN 'done' THEN 'done'
           WHEN 'skipped' THEN 'skipped'
           WHEN 'failed' THEN 'failed'
           WHEN 'dispatched' THEN 'dispatched'
           WHEN 'running' THEN 'running'
           WHEN 'blocked' THEN 'running'
           ELSE 'pending'
       END,
       CASE WHEN n.state = 'dispatched' THEN n.updated_at ELSE NULL END,
       CASE WHEN n.state IN ('running', 'blocked') THEN n.updated_at ELSE NULL END,
       CASE WHEN n.state IN ('done', 'skipped', 'failed') THEN n.updated_at ELSE NULL END
FROM task_nodes n
JOIN task_tasks t ON t.task_id = n.task_id
WHERE NOT EXISTS (
    SELECT 1 FROM task_node_runs r
    WHERE r.task_id = n.task_id AND r.node_id = n.node_id AND r.attempt_no = 1
);

UPDATE task_nodes
SET current_run_id = 'run_legacy_' || task_id || '_' || node_id;
