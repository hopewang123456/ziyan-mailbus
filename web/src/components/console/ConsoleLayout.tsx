import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { NavGroup } from "../../lib/navigation";

/**
 * 管理中心布局（P4）：结构化分组侧栏 + wide/fluid 内容宽度。
 * 视觉与孪生大屏保持分野：固定侧栏、无装饰背景。
 */
export function ConsoleLayout({
  groups,
  children,
  onLogout,
  logoutBusy,
  width = "default",
}: {
  groups: NavGroup[];
  children: ReactNode;
  onLogout?: () => void;
  logoutBusy?: boolean;
  width?: "default" | "wide" | "fluid";
}) {
  const widthClass =
    width === "fluid"
      ? "max-w-none"
      : width === "wide"
        ? "max-w-[1600px]"
        : "max-w-5xl";

  return (
    <div className="flex min-h-screen bg-abyss text-frost">
      <aside className="fixed inset-y-0 left-0 z-40 flex w-56 flex-col border-r border-rail bg-hull">
        <div className="border-b border-rail px-4 py-4">
          <p className="font-display text-sm font-semibold tracking-tight text-frost">mailbus</p>
          <p className="mt-0.5 text-[11px] text-mute">管理中心 · Console</p>
        </div>
        <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-3" aria-label="管理导航">
          {groups.map((group) => (
            <div key={group.key}>
              <p className="px-3 pb-1 text-[10px] font-medium uppercase tracking-wider text-mute/70">
                {group.label}
              </p>
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <ConsoleNavItem
                    key={item.key}
                    to={item.to}
                    icon={item.icon}
                    label={item.label}
                    end={item.exact}
                  />
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="space-y-2 border-t border-rail px-4 py-3">
          <a href="/twin" className="block text-[11px] text-mute transition hover:text-frost">
            孪生大屏 →
          </a>
          {onLogout && (
            <button
              type="button"
              className="w-full rounded border border-rail px-2 py-1 text-left text-[11px] text-mute transition hover:text-frost disabled:opacity-40"
              disabled={logoutBusy}
              onClick={onLogout}
            >
              {logoutBusy ? "正在退出…" : "退出登录"}
            </button>
          )}
        </div>
      </aside>
      <main className="ml-56 min-w-0 flex-1">
        <div className={`mx-auto px-6 py-6 ${widthClass}`}>{children}</div>
      </main>
    </div>
  );
}

export function ConsoleNavItem({
  to,
  icon,
  label,
  end,
}: {
  to: string;
  icon: string;
  label: string;
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        [
          "flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] transition",
          isActive ? "bg-rail font-medium text-frost" : "text-mute hover:bg-rail/40 hover:text-frost",
        ].join(" ")
      }
    >
      <span aria-hidden className="w-4 text-center text-sm">
        {icon}
      </span>
      {label}
    </NavLink>
  );
}
