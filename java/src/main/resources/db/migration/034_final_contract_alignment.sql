-- 034 最终契约对齐：扇出槽位、Graph 乐观锁、软删除、endpoint 审批、token 反查、邀请字段。
-- token 列自此只存应用加密后的密文。明文迁移由持有 MAILBUS_TOKEN_ENCRYPTION_KEY 的应用步骤执行。
-- 本文件不写入密钥、明文或任何伪造哈希。

-- 1. 重建 task_node_runs，新增 fanout_slot，旧数据全部回填 0。
--    保留 run_id / result / attempt / artifacts 引用，唯一键加入 fanout_slot。
CREATE TABLE task_node_runs_new (
    run_id               TEXT PRIMARY KEY,
    task_id              TEXT NOT NULL,
    node_id              TEXT NOT NULL,
    attempt_no           INTEGER NOT NULL,
    fanout_slot          INTEGER NOT NULL DEFAULT 0,
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
    UNIQUE (task_id, node_id, fanout_slot, attempt_no)
);

INSERT INTO task_node_runs_new (
    run_id, task_id, node_id, attempt_no, fanout_slot, assigned_employee_id,
    role_id, state, fanout_group, short_fanout, result, parent_run_id,
    dispatched_at, started_at, completed_at, deadline_at, escalated_at
)
SELECT run_id, task_id, node_id, attempt_no, 0, assigned_employee_id,
       role_id, state, fanout_group, short_fanout, result, parent_run_id,
       dispatched_at, started_at, completed_at, deadline_at, escalated_at
FROM task_node_runs;

DROP TABLE task_node_runs;

ALTER TABLE task_node_runs_new RENAME TO task_node_runs;

CREATE INDEX IF NOT EXISTS idx_task_node_runs_task
    ON task_node_runs (task_id, node_id);
CREATE INDEX IF NOT EXISTS idx_task_node_runs_employee
    ON task_node_runs (assigned_employee_id, state);
CREATE INDEX IF NOT EXISTS idx_task_node_runs_deadline
    ON task_node_runs (state, deadline_at);
CREATE INDEX IF NOT EXISTS idx_task_node_runs_fanout
    ON task_node_runs (task_id, fanout_group, fanout_slot, attempt_no);

-- 2. Graph 乐观锁：整数 revision，旧版本从 1 开始。
ALTER TABLE wf_versions ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;

-- 3. 软删除：员工、工作流、Agent 默认列表过滤，历史任务与审批保留。
ALTER TABLE identity_employees ADD COLUMN deleted_at REAL;
ALTER TABLE identity_employees ADD COLUMN deleted_by TEXT;

ALTER TABLE wf_defs ADD COLUMN deleted_at REAL;
ALTER TABLE wf_defs ADD COLUMN deleted_by TEXT;

ALTER TABLE agents ADD COLUMN deleted_at REAL;
ALTER TABLE agents ADD COLUMN deleted_by TEXT;

-- 4. Agent endpoint 审批：新上报地址先进入 pending_endpoint，管理员批准后才成为权威 endpoint。
ALTER TABLE agents ADD COLUMN pending_endpoint TEXT;
ALTER TABLE agents ADD COLUMN endpoint_review_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE agents ADD COLUMN endpoint_approved_by TEXT;
ALTER TABLE agents ADD COLUMN endpoint_approved_at REAL;

UPDATE agents
SET endpoint_review_status = 'approved',
    endpoint_approved_at = updated_at
WHERE endpoint IS NOT NULL AND TRIM(endpoint) <> '';

-- 5. Token 密文与入站反查 digest。原明文唯一索引不再承担入站查询。
ALTER TABLE agents ADD COLUMN endpoint_token_lookup_hash TEXT;
ALTER TABLE agents ADD COLUMN endpoint_token_prev_lookup_hash TEXT;

DROP INDEX IF EXISTS idx_agents_endpoint_token;
DROP INDEX IF EXISTS idx_agents_endpoint_token_prev;

CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_endpoint_token_lookup
    ON agents (endpoint_token_lookup_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_endpoint_token_prev_lookup
    ON agents (endpoint_token_prev_lookup_hash);

-- 6. 邀请上界与撤销字段。
ALTER TABLE agent_registration_invites ADD COLUMN data_scope TEXT NOT NULL DEFAULT 'self';

ALTER TABLE identity_invites ADD COLUMN revoked_at REAL;
ALTER TABLE identity_invites ADD COLUMN revoked_by TEXT;
