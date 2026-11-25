import { useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

export interface ConsoleTabItem<T extends string = string> {
  key: T;
  label: ReactNode;
  badge?: number;
}

/**
 * Tab 与 URL 同步：可分享、刷新保持；未知值回落到默认页签。
 */
export function useTabParam<T extends string>(
  allowed: readonly T[],
  fallback: T,
): [T, (next: T) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab") as T | null;
  const current = raw && allowed.includes(raw) ? raw : fallback;
  const setTab = (next: T) => {
    setParams(
      (prev) => {
        const copy = new URLSearchParams(prev);
        copy.set("tab", next);
        return copy;
      },
      { replace: true },
    );
  };
  return [current, setTab];
}

export function ConsoleTabs<T extends string>({
  tabs,
  value,
  onChange,
  ariaLabel = "页面页签",
}: {
  tabs: ConsoleTabItem<T>[];
  value: T;
  onChange: (next: T) => void;
  ariaLabel?: string;
}) {
  const items = useMemo(() => tabs, [tabs]);
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="mb-4 flex flex-wrap items-center gap-1 border-b border-rail"
    >
      {items.map((tab) => {
        const active = tab.key === value;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.key)}
            className={[
              "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] transition",
              active
                ? "border-mint text-frost"
                : "border-transparent text-mute hover:text-frost",
            ].join(" ")}
          >
            {tab.label}
            {typeof tab.badge === "number" && tab.badge > 0 && (
              <span className="rounded-full bg-rail px-1.5 py-0.5 font-mono text-[10px] text-frost">
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
