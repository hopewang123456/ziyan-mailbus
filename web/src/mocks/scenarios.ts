/**
 * mock 场景：通过 URL `?scene=` 切换，仅 `VITE_API_MODE=mock` 时启用。
 * B1.5 契约桩导出前，这里不声明领域 DTO；仅按冻结路径返回同构 JSON。
 */

export type MockScene = "staff" | "super" | "supervisor" | "readonly" | "conflict" | "offline";

const SCENES: MockScene[] = ["staff", "super", "supervisor", "readonly", "conflict", "offline"];

export function currentScene(): MockScene {
  if (typeof window === "undefined") return "staff";
  const value = new URLSearchParams(window.location.search).get("scene");
  return SCENES.includes(value as MockScene) ? (value as MockScene) : "staff";
}

export function scenePermissions(scene: MockScene): string[] {
  switch (scene) {
    case "super":
      return ["*"];
    case "supervisor":
      return [
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
      ];
    case "readonly":
      return ["message_read"];
    case "conflict":
    case "offline":
    case "staff":
    default:
      return ["message_read", "task_create", "result_submit", "hitl_request"];
  }
}

export function sceneScope(scene: MockScene): "self" | "team" | "global" {
  if (scene === "super") return "global";
  if (scene === "supervisor") return "team";
  return "self";
}
