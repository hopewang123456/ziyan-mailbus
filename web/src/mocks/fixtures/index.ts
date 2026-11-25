/** 固定 fixtures：时间一律 ISO 8601 UTC，分页统一 {items,total,limit,offset}。 */

export const NOW = "2026-11-25T08:00:00.000Z";

export function iso(offsetSeconds: number): string {
  return new Date(Date.parse(NOW) + offsetSeconds * 1000).toISOString();
}

export const employee = {
  employee_id: "emp_1001",
  display_name: "林岸",
  state: "active",
  data_scope: "self",
};

export const taskSummary = {
  claimable: 3,
  mine_open: 2,
  approvals: 1,
};

export const overview = {
  employees_total: 24,
  employees_active: 21,
  employees_pending: 2,
  employees_offline: 1,
  agents_total: 6,
  agents_enabled: 5,
  agents_online: 4,
  agents_busy: 2,
  teams: 4,
  positions: 9,
  seats_occupied: 18,
  tasks_total: 42,
  tasks_active: 7,
  tasks_running: 3,
  tasks_blocked: 1,
  tasks_done: 31,
  tasks_failed_today: 0,
  approvals_pending: 1,
  messages_total: 128,
  workflows_total: 5,
  workflows_published: 3,
  skills_total: 8,
  skills_enabled: 6,
};

export const health = {
  status: "ok",
  service: "mailbus",
  version: "0.1.0-mock",
  schema_version: 36,
};

export const screens = [
  {
    screen_id: "screen_01",
    name: "前台大屏",
    source: "twin",
    online: true,
    last_seen_at: iso(-12),
    config_version: 4,
    published_config_version: 4,
    team_bound: true,
    play_state: "playing",
  },
  {
    screen_id: "screen_02",
    name: "研发区大屏",
    source: "console",
    online: false,
    last_seen_at: iso(-3600),
    config_version: 2,
    published_config_version: 1,
    team_bound: false,
    play_state: "paused",
  },
];
