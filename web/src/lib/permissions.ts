/**
 * 唯一权限判断落点。页面只通过 `can()` / `canAny()` 判断，
 * 不直接读取 permissions 数组，避免权限点字符串散落各页。
 */

export type DataScope = "self" | "team" | "global";

export const DATA_SCOPES: DataScope[] = ["self", "team", "global"];

export const DATA_SCOPE_LABELS: Record<DataScope, string> = {
  self: "仅本人",
  team: "本团队",
  global: "全部",
};

export type Permission =
  | "message_read"
  | "message_send"
  | "task_create"
  | "task_dispatch"
  | "result_submit"
  | "hitl_request"
  | "hitl_resolve"
  | "workflow_create"
  | "workflow_modify"
  | "workflow_publish"
  | "employee_invite"
  | "employee_remove"
  | "org_manage"
  | "role_manage"
  | "role_bind"
  | "agent_deregister"
  | "log_read"
  | "system_config"
  | "console_admin"
  | "escalation_resolve"
  | "artifact_read_all";

export interface PermissionMeta {
  key: Permission;
  label: string;
  description: string;
}

export interface PermissionGroup {
  key: "collab" | "process" | "org" | "ops";
  label: string;
  permissions: PermissionMeta[];
}

export const PERMISSION_GROUPS: PermissionGroup[] = [
  {
    key: "collab",
    label: "协作",
    permissions: [
      { key: "message_read", label: "读消息", description: "查看消息与追迹" },
      { key: "message_send", label: "发消息", description: "发送协同消息" },
      { key: "task_create", label: "创建任务", description: "创建本人任务" },
      { key: "task_dispatch", label: "派发任务", description: "指定他人或代派任务" },
      { key: "result_submit", label: "提交结果", description: "提交节点结果与产物" },
      { key: "hitl_request", label: "发起人工介入", description: "发起审批或人工处理" },
      { key: "hitl_resolve", label: "处理审批", description: "通过/驳回审批与人工介入" },
    ],
  },
  {
    key: "process",
    label: "流程",
    permissions: [
      { key: "workflow_create", label: "新建工作流", description: "创建工作流与首版" },
      { key: "workflow_modify", label: "编辑工作流", description: "编辑草稿、派生版本、删除" },
      { key: "workflow_publish", label: "发布版本", description: "发布工作流版本" },
    ],
  },
  {
    key: "org",
    label: "组织",
    permissions: [
      { key: "employee_invite", label: "邀请真人", description: "创建与重发真人邀请" },
      { key: "employee_remove", label: "移除员工", description: "软移除员工" },
      { key: "org_manage", label: "组织管理", description: "岗位/团队/工位管理" },
      { key: "role_manage", label: "角色管理", description: "业务角色 CRUD" },
      { key: "role_bind", label: "绑定角色", description: "岗位/员工绑定角色" },
      { key: "agent_deregister", label: "注销 Agent", description: "注销 Agent 外壳" },
    ],
  },
  {
    key: "ops",
    label: "运维",
    permissions: [
      { key: "log_read", label: "审计日志", description: "查看审计与告警" },
      { key: "system_config", label: "系统配置", description: "集成、设置、技能包" },
      { key: "console_admin", label: "控制台超管", description: "等价全部权限" },
      { key: "escalation_resolve", label: "处理升级", description: "处理超时升级" },
      { key: "artifact_read_all", label: "读取全部产物", description: "下载任意任务产物" },
    ],
  },
];

export const ALL_PERMISSIONS: Permission[] = PERMISSION_GROUPS.flatMap((group) =>
  group.permissions.map((item) => item.key),
);

export const PERMISSION_LABELS: Record<Permission, string> = Object.fromEntries(
  PERMISSION_GROUPS.flatMap((group) =>
    group.permissions.map((item) => [item.key, item.label]),
  ),
) as Record<Permission, string>;

export type PermissionTemplateKey = "super_admin" | "supervisor" | "staff" | "readonly";

export interface PermissionTemplate {
  key: PermissionTemplateKey;
  label: string;
  permissions: Permission[];
  dataScope: DataScope;
}

export const PERMISSION_TEMPLATES: PermissionTemplate[] = [
  {
    key: "super_admin",
    label: "超管",
    permissions: ["console_admin"],
    dataScope: "global",
  },
  {
    key: "supervisor",
    label: "主管",
    permissions: [
      "message_read",
      "message_send",
      "task_create",
      "task_dispatch",
      "result_submit",
      "hitl_request",
      "hitl_resolve",
      "workflow_create",
      "workflow_modify",
      "role_bind",
      "escalation_resolve",
      "artifact_read_all",
    ],
    dataScope: "team",
  },
  {
    key: "staff",
    label: "员工",
    permissions: [
      "message_read",
      "message_send",
      "task_create",
      "result_submit",
      "hitl_request",
    ],
    dataScope: "self",
  },
  {
    key: "readonly",
    label: "只读",
    permissions: ["message_read"],
    dataScope: "self",
  },
];

/** `console_admin` 与 `*` 等价于全部权限。 */
export function can(permissions: readonly string[] | undefined, target: Permission): boolean {
  if (!permissions || permissions.length === 0) return false;
  return permissions.includes("*") || permissions.includes("console_admin") || permissions.includes(target);
}

export function canAny(
  permissions: readonly string[] | undefined,
  targets: readonly Permission[],
): boolean {
  if (!permissions || permissions.length === 0) return false;
  if (permissions.includes("*") || permissions.includes("console_admin")) return true;
  return targets.some((target) => permissions.includes(target));
}

export function canAll(
  permissions: readonly string[] | undefined,
  targets: readonly Permission[],
): boolean {
  if (!permissions || permissions.length === 0) return false;
  if (permissions.includes("*") || permissions.includes("console_admin")) return true;
  return targets.every((target) => permissions.includes(target));
}

/** 超管/`console_admin` 只授 `console_admin`；模板用于快速套用后可微调。 */
export function templatePermissions(key: PermissionTemplateKey): Permission[] {
  return PERMISSION_TEMPLATES.find((item) => item.key === key)?.permissions ?? [];
}
