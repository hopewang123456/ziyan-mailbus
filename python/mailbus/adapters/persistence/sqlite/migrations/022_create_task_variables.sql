-- 022 任务实例变量。
CREATE TABLE IF NOT EXISTS task_variables (
    task_id    TEXT NOT NULL,
    var_key    TEXT NOT NULL,
    var_value  TEXT NOT NULL,
    source     TEXT NOT NULL CHECK (source IN ('input', 'system')),
    updated_by TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (task_id, var_key)
);
