import { useEffect, useRef, type ReactNode } from "react";
import { t } from "../lib/i18n";

type Props = {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  /** portrait：宽幅名片，去内边距让头像铺满 */
  variant?: "default" | "portrait";
};

/** L3 业务弹层 */
export function HudL3Modal({ title, open, onClose, children, variant = "default" }: Props) {
  const sheetRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab" || !sheetRef.current) return;
      const nodes = sheetRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    const focusable = sheetRef.current?.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    focusable?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const sheetClass =
    variant === "portrait" ? "cp-l3-sheet cp-l3-sheet--portrait" : "cp-l3-sheet";
  return (
    <div className="cp-l3" role="dialog" aria-modal="true" aria-label={title}>
      <div className="cp-l3-backdrop" onClick={onClose} />
      <div ref={sheetRef} className={sheetClass} data-surface="form">
        <header className="cp-l3-head">
          <h3>{title}</h3>
          <button type="button" className="cp-icon-x" aria-label={t("close")} onClick={onClose}>
            ×
          </button>
        </header>
        <div className="cp-l3-body">{children}</div>
      </div>
    </div>
  );
}
