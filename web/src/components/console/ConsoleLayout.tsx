import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

/**
 * 管理中心布局（P3，D6：协同管理后台——正经表格表单范式）。
 *
 * 与驾驶舱 Shell 的视觉分野：无星空/星云/3D 装饰；固定侧栏 + 顶栏 + 内容区
 * 的标准后台结构；沿用 mailbus 色板（abyss/hull/rail/frost/mute/mint）保持品牌一致。
 */
export function ConsoleLayout({ nav, children }: { nav: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-abyss text-frost">
      <aside className="fixed inset-y-0 left-0 z-40 flex w-56 flex-col border-r border-rail bg-hull">
        <div className="border-b border-rail px-4 py-4">
          <p className="font-display text-sm font-semibold tracking-tight text-frost">mailbus</p>
          <p className="mt-0.5 text-[11px] text-mute">管理中心 · Console</p>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3" aria-label="管理导航">
          {nav}
        </nav>
        <div className="border-t border-rail px-4 py-3">
          <a href="/" className="text-[11px] text-mute transition hover:text-frost">
            ← 返回驾驶舱
          </a>
        </div>
      </aside>
      <main className="ml-56 min-w-0 flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">{children}</div>
      </main>
    </div>
  );
}

export function ConsoleNavItem({ to, icon, label }: { to: string; icon: string; label: string }) {
  return (
    <NavLink
      to={to}
      end
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
