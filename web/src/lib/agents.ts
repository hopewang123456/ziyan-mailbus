/** Shared agent types (extracted so FleetGrid can be removed). */

export type AgentRow = {
  id: string;
  name?: string;
  role?: string;
  type?: string;
  framework?: string;
  archetype?: string;
  models?: string[];
  launch_modes?: string[];
  has_browser?: boolean;
  has_desktop?: boolean;
  launch_url?: string;
  enabled?: boolean;
  active_tasks?: number;
  queued_steps?: number;
  inbox_pending?: number;
  [k: string]: unknown;
};

export type OrbitFilter =
  | "all"
  | "hermes"
  | "openclaw"
  | "opencode"
  | "codex"
  | "claude";

/** Map backend framework to orbit filter chip / segment id. */
export function agentFrameworkLabel(agent: AgentRow): string | null {
  const raw = String(agent.framework || agent.type || "").toLowerCase();
  if (!raw || raw === "?") return null;
  if (raw === "hermes_profile" || raw === "hermes") return "hermes";
  if (raw === "openclaw") return "openclaw";
  if (raw === "opencode") return "opencode";
  if (raw === "codex") return "codex";
  if (raw === "claude" || raw === "claude_code" || raw === "claude-code") return "claude";
  return raw;
}

export function agentOrbitBucket(agent: AgentRow): OrbitFilter | "other" {
  const fw = agentFrameworkLabel(agent);
  if (
    fw === "hermes" ||
    fw === "openclaw" ||
    fw === "opencode" ||
    fw === "codex" ||
    fw === "claude"
  ) {
    return fw;
  }
  return "other";
}

export function matchesOrbitFilter(agent: AgentRow, filter: OrbitFilter): boolean {
  if (filter === "all") return true;
  return agentOrbitBucket(agent) === filter;
}

export type AgentProfile = {
  config?: Record<string, unknown>;
  card?: {
    name?: string;
    role?: string;
    age?: string | number;
    zodiac?: string;
    mbti?: string;
    gender?: string;
    motto?: string;
    traits?: string[];
    personality?: string;
    strengths?: string;
    weaknesses?: string;
    abilities?: string;
    catchphrases?: string[];
    bond?: string;
    ziyan_bond?: string;
    social?: string;
    animated?: string;
    archetype?: string;
  };
  identity?: string;
  soul?: string;
  skills?: string[];
  messages?: number;
  unread?: number;
  avatar_url?: string;
  avatar_animated?: string;
};
