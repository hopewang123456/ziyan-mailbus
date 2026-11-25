import { employee, health, overview, screens, taskSummary } from "./fixtures";
import { currentScene, scenePermissions, sceneScope } from "./scenarios";

/**
 * 开发 mock 路由：只按冻结路径返回同构 JSON，不引入第二套 DTO。
 * 未登记接口返回 404，避免“假成功”掩盖契约缺口。
 */

const encoder = new TextEncoder();

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function empty(status = 204): Response {
  return new Response(null, { status });
}

function error(status: number, errorCode: string, messageZh: string): Response {
  return json({ error: errorCode, error_code: errorCode, message_zh: messageZh }, status);
}

function bodyOf(init?: RequestInit): Record<string, unknown> {
  try {
    if (typeof init?.body === "string") return JSON.parse(init.body) as Record<string, unknown>;
  } catch {
    // 忽略坏 body
  }
  return {};
}

function headerOf(init: RequestInit | undefined, name: string): string {
  const headers = new Headers(init?.headers || {});
  return headers.get(name) ?? "";
}

function sse(): Response {
  let timer: number | undefined;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(": mock stream connected\n\n"));
      timer = window.setInterval(() => {
        try {
          controller.enqueue(encoder.encode(": ping\n\n"));
        } catch {
          if (timer) window.clearInterval(timer);
        }
      }, 15_000);
    },
    cancel() {
      if (timer) window.clearInterval(timer);
    },
  });
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}

export function handleMock(method: string, url: URL, init?: RequestInit): Response {
  const scene = currentScene();
  const path = url.pathname;

  if (path.endsWith("/stream")) return sse();

  if (scene === "offline") {
    return error(503, "service_unavailable", "服务暂时不可用（mock offline）");
  }
  if (scene === "conflict" && method !== "GET" && method !== "HEAD") {
    return error(409, "conflict", "版本冲突，请刷新后重试（mock conflict）");
  }

  if (method === "GET" && path === "/api/identity/bootstrap") {
    return json({
      steps: [
        { step: "super_admin", done: true },
        { step: "sample_team", done: false },
      ],
    });
  }

  if (method === "GET" && path === "/api/identity/me") {
    return json({
      ...employee,
      permissions: scenePermissions(scene),
      data_scope: sceneScope(scene),
    });
  }

  if (method === "POST" && /\/api\/identity\/staff\/[^/]+\/heartbeat$/.test(path)) {
    return json({ ok: true });
  }

  if (method === "POST" && path === "/api/identity/logout") {
    return json({ ok: true });
  }

  if (method === "GET" && path === "/api/tasks/summary") {
    return json(taskSummary);
  }

  if (method === "GET" && path === "/api/overview") {
    return json(overview);
  }

  if (method === "GET" && path === "/api/health") {
    return json(health);
  }

  if (path === "/api/public/collab/screens" && method === "POST") {
    const body = bodyOf(init);
    const fallbackId = `screen_${Math.random().toString(36).slice(2, 10)}`;
    const screenId = typeof body.screen_id === "string" && body.screen_id ? body.screen_id : fallbackId;
    const hasSecret = typeof body.secret === "string" && body.secret.length > 0;
    return json({
      screen_id: screenId,
      // 复用已有密钥时不回显；新建或密钥缺失才返回一次性明文
      ...(hasSecret ? {} : { screen_secret: `sec_${screenId}` }),
      config_version: 1,
    });
  }

  const screenAction = /^\/api\/(?:public\/)?collab\/screens\/([^/]+)\/(heartbeat|leave|config)$/.exec(
    path,
  );
  if (screenAction) {
    const [, screenId, action] = screenAction;
    const secret = headerOf(init, "X-Screen-Secret");
    if (action === "config") {
      return json({
        screen_id: screenId,
        config_version: 1,
        published: true,
        layout_type: "office",
        theme: "auto",
        resolution: "auto",
        team_bound: false,
        play_state: "playing",
      });
    }
    if (!secret && action === "heartbeat") {
      return error(403, "screen_secret_invalid", "缺少屏幕密钥（X-Screen-Secret）");
    }
    if (action === "leave") return empty();
    return json({ ok: true });
  }

  if (method === "GET" && path === "/api/collab/screens") {
    return json({
      items: screens,
      total: screens.length,
      limit: 100,
      offset: 0,
    });
  }

  if (method === "GET" && path === "/api/public/layout") {
    return json({ floors: [], seats: [], pair_lines: [], updated_at: null });
  }

  return error(404, "mock_not_found", `mock 未登记该接口：${method} ${path}`);
}
