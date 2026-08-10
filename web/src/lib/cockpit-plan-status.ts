/** Lightweight plan-status helpers for cockpit HUD badges. */

export type PlanLane = "idle" | "running" | "blocked" | "done" | "unknown";

export function laneFromTaskStatus(status: string | undefined | null): PlanLane {
  const s = (status ?? "").toLowerCase();
  if (!s) return "unknown";
  if (["done", "completed", "success", "closed"].includes(s)) return "done";
  if (["blocked", "waiting_human", "human", "paused"].includes(s)) return "blocked";
  if (["running", "in_progress", "active", "queued", "pending"].includes(s)) return "running";
  if (["idle", "draft", "new"].includes(s)) return "idle";
  return "unknown";
}

export function laneLabel(lane: PlanLane): string {
  switch (lane) {
    case "idle":
      return "空闲";
    case "running":
      return "进行中";
    case "blocked":
      return "阻塞";
    case "done":
      return "完成";
    default:
      return "未知";
  }
}
