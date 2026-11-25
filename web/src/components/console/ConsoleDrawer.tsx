import { useId, useRef, type ReactNode } from "react";
import { useFocusTrap } from "./ConsoleDialog";

export interface ConsoleDrawerProps {
  open: boolean;
  title: ReactNode;
  description?: ReactNode;
  width?: 560 | 640;
  onClose: () => void;
  footer?: ReactNode;
  children: ReactNode;
}

/** 右侧抽屉：560/640px，焦点圈定、Esc 关闭、关闭后焦点返回。 */
export function ConsoleDrawer({
  open,
  title,
  description,
  width = 560,
  onClose,
  footer,
  children,
}: ConsoleDrawerProps) {
  const panelRef = useRef<HTMLElement>(null);
  useFocusTrap(open, panelRef, onClose);
  const titleId = useId();
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60]">
      <div className="absolute inset-0 bg-abyss/60" onClick={onClose} aria-hidden />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="absolute inset-y-0 right-0 flex max-w-full flex-col border-l border-rail bg-hull shadow-2xl outline-none"
        style={{ width }}
      >
        <header className="flex items-start justify-between gap-3 border-b border-rail px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="truncate font-display text-base text-frost">
              {title}
            </h2>
            {description && <p className="mt-1 text-xs text-mute">{description}</p>}
          </div>
          <button
            type="button"
            aria-label="关闭"
            className="rounded border border-rail px-2 py-1 text-xs text-mute transition hover:text-frost"
            onClick={onClose}
          >
            ✕
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="border-t border-rail px-5 py-3">{footer}</footer>}
      </aside>
    </div>
  );
}
