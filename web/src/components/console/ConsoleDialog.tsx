import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";

/** 焦点圈定：打开时聚焦面板，Tab 循环，关闭后焦点返回触发元素。 */
export function useFocusTrap(
  open: boolean,
  panelRef: RefObject<HTMLElement | null>,
  onClose: () => void,
): void {
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const focusable = () =>
      Array.from(
        panel?.querySelectorAll<HTMLElement>(
          'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((element) => element.offsetParent !== null);

    const first = focusable()[0];
    (first ?? panel)?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) return;
      const head = items[0];
      const tail = items[items.length - 1];
      if (event.shiftKey && document.activeElement === head) {
        event.preventDefault();
        tail.focus();
      } else if (!event.shiftKey && document.activeElement === tail) {
        event.preventDefault();
        head.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus?.();
    };
  }, [open, panelRef, onClose]);
}

/** 通用对话框：焦点圈定、Esc 关闭、关闭后焦点返回。 */
export function Dialog({
  open,
  title,
  description,
  onClose,
  footer,
  children,
  width = 520,
}: {
  open: boolean;
  title: string;
  description?: ReactNode;
  onClose: () => void;
  footer?: ReactNode;
  children?: ReactNode;
  width?: number;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(open, panelRef, onClose);
  const titleId = useId();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-abyss/70" onClick={onClose} aria-hidden />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="relative w-full rounded-lg border border-rail bg-hull p-5 shadow-2xl outline-none"
        style={{ maxWidth: width }}
      >
        <h2 id={titleId} className="font-display text-base text-frost">{title}</h2>
        {description && <p className="mt-1 text-xs text-mute">{description}</p>}
        {children && <div className="mt-4">{children}</div>}
        {footer && <div className="mt-5 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 危险操作统一确认，不单独拼浏览器 confirm。 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  danger,
  busy,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(open, panelRef, onCancel);
  const titleId = useId();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-abyss/70" onClick={onCancel} aria-hidden />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="relative w-full max-w-md rounded-lg border border-rail bg-hull p-5 shadow-2xl outline-none"
      >
        <h2 id={titleId} className="font-display text-base text-frost">
          {title}
        </h2>
        {description && <div className="mt-2 text-xs leading-relaxed text-mute">{description}</div>}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            className="rounded border border-rail px-3 py-1.5 text-xs text-mute transition hover:text-frost disabled:opacity-40"
            disabled={busy}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={[
              "rounded px-3 py-1.5 text-xs transition disabled:opacity-40",
              danger ? "bg-flare text-abyss hover:opacity-90" : "bg-mint text-abyss hover:opacity-90",
            ].join(" ")}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "处理中…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
