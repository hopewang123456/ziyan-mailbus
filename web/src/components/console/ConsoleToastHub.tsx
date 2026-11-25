import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 全局 Toast：合并原 WriteFailToast 的写失败事件，并提供统一 pushToast。
 * 页面仍只关心业务文案；网络/权限错误由 api.ts 统一派发。
 */

export type ToastTone = "error" | "success" | "info";

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

const TOAST_EVENT = "mailbus:toast";
const WRITE_FAILED_EVENT = "mailbus:write-failed";
const DISMISS_MS = 6000;

export function pushToast(message: string, tone: ToastTone = "info"): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(TOAST_EVENT, { detail: { message, tone } }));
}

export function ConsoleToastHub() {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) window.clearTimeout(timer);
    timers.current.delete(id);
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const enqueue = useCallback(
    (message: string, tone: ToastTone) => {
      if (!message) return;
      const id = nextId.current++;
      setItems((prev) => {
        if (prev.some((item) => item.message === message && item.tone === tone)) return prev;
        return [...prev, { id, message, tone }].slice(-4);
      });
      timers.current.set(
        id,
        window.setTimeout(() => dismiss(id), DISMISS_MS),
      );
    },
    [dismiss],
  );

  useEffect(() => {
    const onToast = (event: Event) => {
      const detail = (event as CustomEvent<{ message?: string; tone?: ToastTone }>).detail;
      enqueue(detail?.message ?? "", detail?.tone ?? "info");
    };
    const onWriteFailed = (event: Event) => {
      const detail = (event as CustomEvent<{ error?: string; status?: number }>).detail;
      enqueue(detail?.error || `写操作失败（HTTP ${detail?.status ?? 0}）`, "error");
    };
    window.addEventListener(TOAST_EVENT, onToast);
    window.addEventListener(WRITE_FAILED_EVENT, onWriteFailed);
    const currentTimers = timers.current;
    return () => {
      window.removeEventListener(TOAST_EVENT, onToast);
      window.removeEventListener(WRITE_FAILED_EVENT, onWriteFailed);
      for (const timer of currentTimers.values()) window.clearTimeout(timer);
      currentTimers.clear();
    };
  }, [enqueue]);

  if (items.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-[min(420px,calc(100vw-2rem))] flex-col gap-2">
      {items.map((item) => (
        <div
          key={item.id}
          role="status"
          className={[
            "pointer-events-auto flex items-start gap-2 rounded-md border px-3 py-2 text-xs shadow-lg backdrop-blur",
            item.tone === "error"
              ? "border-flare/50 bg-abyss/95 text-flare"
              : item.tone === "success"
                ? "border-mint/50 bg-abyss/95 text-mint"
                : "border-rail bg-abyss/95 text-frost",
          ].join(" ")}
        >
          <span className="flex-1 leading-relaxed">{item.message}</span>
          <button
            type="button"
            aria-label="关闭提示"
            className="shrink-0 text-mute transition hover:text-frost"
            onClick={() => dismiss(item.id)}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
