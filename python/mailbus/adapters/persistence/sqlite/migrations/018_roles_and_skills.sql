-- 018 角色、业务技能与岗位绑定。
-- capabilities 均为业务技能标签（JSON 数组或单值），与权限 permission 无关。
CREATE TABLE IF NOT EXISTS agent_roles (
    role_id      TEXT PRIMARY KEY,
    role_name    TEXT NOT NULL,
    capabilities TEXT NOT NULL DEFAULT '[]',
    description  TEXT,
    enabled      INTEGER NOT NULL DEFAULT 1,
    icon         TEXT,
    color        TEXT,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS employee_capabilities (
    employee_id TEXT NOT NULL,
    capability  TEXT NOT NULL,
    source      TEXT NOT NULL,
    granted_at  REAL NOT NULL,
    PRIMARY KEY (employee_id, capability)
);

CREATE TABLE IF NOT EXISTS employee_role_bindings (
    employee_id TEXT NOT NULL,
    role_id     TEXT NOT NULL,
    PRIMARY KEY (employee_id, role_id)
);

CREATE TABLE IF NOT EXISTS position_role_bindings (
    position_id TEXT NOT NULL,
    role_id     TEXT NOT NULL,
    PRIMARY KEY (position_id, role_id)
);

CREATE TABLE IF NOT EXISTS position_employee_assignments (
    position_id TEXT NOT NULL,
    role_id     TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    PRIMARY KEY (position_id, role_id)
);

CREATE TABLE IF NOT EXISTS employee_contacts (
    employee_id   TEXT NOT NULL,
    contact_type  TEXT NOT NULL,
    contact_value TEXT NOT NULL,
    PRIMARY KEY (employee_id, contact_type)
);

-- 调度热路径：按业务技能找候选员工、按角色反查绑定。
CREATE INDEX IF NOT EXISTS idx_employee_capabilities_capability
    ON employee_capabilities (capability);
CREATE INDEX IF NOT EXISTS idx_employee_role_bindings_role
    ON employee_role_bindings (role_id);
CREATE INDEX IF NOT EXISTS idx_position_role_bindings_role
    ON position_role_bindings (role_id);
CREATE INDEX IF NOT EXISTS idx_agent_roles_enabled
    ON agent_roles (enabled);
