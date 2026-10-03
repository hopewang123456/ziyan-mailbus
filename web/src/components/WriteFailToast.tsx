import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

type WriteFailDetail = {
  path?: string;
  status?: number;
  error?: string;
  method?: string;
};

type Toast = WriteFailDetail & { at: number };

const MAX_TOASTS = 3;
const TOAST_TTL_MS = 8000;

function shortPath(path?: string): string {
  if (!path) return "";
  return path.replace(/^\/api\//, "").slice(0, 48);
}

/**
 * M3 UX 债：写操作失败的全局 toast（此前错误只落在页面角落的小字，
 * 驾驶舱验收按钮失败曾被当作「点了没反应」）。api() 层在写方法
 * 失败时派 mailbus:write-failed，这里聚合并展示。
 */
export function WriteFailToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const onFail = (e: Event) => {
      const d = ((e as CustomEvent).detail || {}) as WriteFailDetail;
      const t: Toast = { ...d, at: Date.now() };
      setToasts((prev) => [...prev.slice(-(MAX_TOASTS - 1)), t]);
    };
    window.addEventListener("mailbus:write-failed", onFail);
    const timer = window.setInterval(() => {
      setToasts((prev) => {
        const next = prev.filter((x) => Date.now() - x.at < TOAST_TTL_MS);
        return next.length === prev.length ? prev : next;
      });
    }, 1000);
    return () => {
      window.removeEventListener("mailbus:write-failed", onFail);
      window.clearInterval(timer);
    };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[95] flex w-[min(92vw,26rem)] flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.at}
          className="pointer-events-auto rounded border border-red-400/60 bg-hull/95 px-3 py-2 text-sm text-frost shadow-lg"
          role="alert"
        >
          <p className="font-medium text-red-400">
            ✗ 写操作失败{t.status ? `（HTTP ${t.status}）` : "（网络错误）"}
          </p>
          <p className="mt-1 break-all text-[12px] leading-snug text-mute">
            {t.method || "POST"} {shortPath(t.path)}
            {t.error ? ` · ${t.error}` : ""}
          </p>
          {t.status === 401 && (
            <p className="mt-1 text-[12px]">
              <Link className="underline decoration-red-400/60 underline-offset-2" to="/">
                去舰桥齿轮旋钮配置 API Token →
              </Link>
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
