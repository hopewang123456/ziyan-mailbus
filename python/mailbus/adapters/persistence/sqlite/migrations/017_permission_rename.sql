-- 017 权限概念重命名：capability → permission。
-- 只改表名/列名，权限值（message_read / message_send / result_submit …）与 granted_at 原样保留。
-- 注意：org_positions.capabilities 与 employee_capabilities.capability 是业务技能，不要改。
ALTER TABLE identity_capability_grants RENAME TO identity_permission_grants;
ALTER TABLE identity_permission_grants RENAME COLUMN capability TO permission;
ALTER TABLE identity_invites RENAME COLUMN capabilities TO permissions;
