import { canAny, type Permission } from "./permissions";

/**
 * 导航与路由可见性的唯一数据源：侧栏分组、页面权限、旧地址重定向
 * 都从这里派生，页面不再各自维护一份判断。
 */

export type NavGroupKey = "workspace" | "collab" | "org" | "process" | "system";

export interface NavItem {
  key: string;
  label: string;
  to: string;
  icon: string;
  /** 为空表示登录即可见。 */
  anyOf?: Permission[];
  /** 仅顶层页面使用精确匹配，其余按路径前缀高亮。 */
  exact?: boolean;
}

export interface NavGroup {
  key: NavGroupKey;
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    key: "workspace",
    label: "工作台",
    items: [
      { key: "overview", label: "概览", to: "/console", icon: "◱", exact: true },
      { key: "metrics", label: "指标与报表", to: "/console/metrics", icon: "◫" },
    ],
  },
  {
    key: "collab",
    label: "协作",
    items: [
      { key: "tasks", label: "任务中心", to: "/console/tasks", icon: "▤" },
      {
        key: "messages",
        label: "消息与追迹",
        to: "/console/messages",
        icon: "✉",
        anyOf: ["message_read"],
      },
      {
        key: "collab",
        label: "协同大屏",
        to: "/console/collab",
        icon: "⇄",
        anyOf: ["console_admin"],
      },
    ],
  },
  {
    key: "org",
    label: "组织",
    items: [
      {
        key: "organization",
        label: "组织",
        to: "/console/organization",
        icon: "☗",
        anyOf: ["org_manage", "employee_invite", "role_manage"],
      },
    ],
  },
  {
    key: "process",
    label: "流程",
    items: [
      { key: "workflows", label: "工作流模板", to: "/console/workflows", icon: "⛓" },
      {
        key: "skills",
        label: "技能包",
        to: "/console/skills",
        icon: "✦",
        anyOf: ["system_config"],
      },
    ],
  },
  {
    key: "system",
    label: "系统",
    items: [
      {
        key: "agents",
        label: "Agent 与接入",
        to: "/console/agents",
        icon: "◈",
        anyOf: ["org_manage", "agent_deregister"],
      },
      {
        key: "integrations",
        label: "集成",
        to: "/console/integrations",
        icon: "⚓",
        anyOf: ["system_config"],
      },
      {
        key: "audit",
        label: "审计与告警",
        to: "/console/audit",
        icon: "⚑",
        anyOf: ["log_read"],
      },
      {
        key: "setup",
        label: "设置向导",
        to: "/console/setup",
        icon: "⚙",
        anyOf: ["system_config"],
      },
    ],
  },
];

export function navItemVisible(item: NavItem, permissions: readonly string[] | undefined): boolean {
  if (!item.anyOf || item.anyOf.length === 0) return true;
  return canAny(permissions, item.anyOf);
}

/** 组内至少一个页面可见才返回该组；空组整组隐藏。 */
export function visibleNavGroups(permissions: readonly string[] | undefined): NavGroup[] {
  const groups: NavGroup[] = [];
  for (const group of NAV_GROUPS) {
    const items = group.items.filter((item) => navItemVisible(item, permissions));
    if (items.length > 0) groups.push({ ...group, items });
  }
  return groups;
}

/** 用于 `RequirePermission`：页面所需权限点的一次性声明。 */
export const PAGE_PERMISSIONS: Record<string, Permission[]> = {
  "/console/metrics": [],
  "/console/tasks": [],
  "/console/messages": ["message_read"],
  "/console/collab": ["console_admin"],
  "/console/organization": ["org_manage", "employee_invite", "role_manage"],
  "/console/workflows": [],
  "/console/skills": ["system_config"],
  "/console/agents": ["org_manage", "agent_deregister"],
  "/console/integrations": ["system_config"],
  "/console/audit": ["log_read"],
  "/console/setup": ["system_config"],
};

/** 旧地址 301 式前端重定向（含控制台内旧路径），避免书签失效与多级跳转。 */
export const LEGACY_REDIRECTS: Array<[string, string]> = [
  ["/console/staff", "/console/organization?tab=staff"],
  ["/console/teams", "/console/organization?tab=teams"],
  ["/console/approvals", "/console/tasks?tab=approvals"],
  ["/collab", "/console/collab"],
  ["/staff", "/console/organization?tab=staff"],
  ["/teams", "/console/organization?tab=teams"],
  ["/approvals", "/console/tasks?tab=approvals"],
  ["/tasks", "/console/tasks"],
  ["/messages", "/console/messages"],
  ["/inbox", "/console/messages"],
  ["/agents", "/console/agents"],
  ["/workflows", "/console/workflows"],
  ["/metrics", "/console/metrics"],
  ["/audit", "/console/audit"],
  ["/integrations", "/console/integrations"],
  ["/skills", "/console/skills"],
  ["/setup", "/console/setup"],
];
