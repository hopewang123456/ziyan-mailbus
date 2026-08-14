import { useState, type ReactNode } from "react";

/** 与「路由 / 内部 LLM」同款：默认收起，点 summary 展开 */
export function SoftFold({
  title,
  hint,
  children,
  defaultOpen = false,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details className="soft-details" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <span className="soft-fold-sum">
          <span className="soft-fold-title">{title}</span>
          {hint ? <span className="soft-fold-hint">{hint}</span> : null}
        </span>
      </summary>
      <div className="soft-fold-body mt-3 space-y-3">{children}</div>
    </details>
  );
}
