import { handleMock } from "./router";

/**
 * 仅开发 + `VITE_API_MODE=mock` 时接管 /api 请求。
 * 生产构建永不进入这里。
 */
export function installMockApi(): void {
  if (typeof window === "undefined" || typeof window.fetch !== "function") return;
  const original = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const raw =
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const url = new URL(raw, window.location.origin);
    if (!url.pathname.startsWith("/api/")) return original(input, init);
    const method = (
      init?.method ?? (input instanceof Request ? input.method : "GET")
    ).toUpperCase();
    const response = handleMock(method, url, init);
    // 模拟网络时延，便于观察加载态
    await new Promise((resolve) => window.setTimeout(resolve, 80));
    return response;
  };
}

export { currentScene, type MockScene } from "./scenarios";
