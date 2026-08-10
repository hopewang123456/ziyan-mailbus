import type { ReactNode } from "react";
import { TwinStarsLogo } from "./TwinStarsLogo";

type Props = {
  nav: ReactNode;
  children: ReactNode;
};

export function Shell({ nav, children }: Props) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-abyss">
      <a href="#main-content" className="skip-link">
        跳到主内容
      </a>
      <div
        className="starfield pointer-events-none absolute inset-0 animate-star-drift"
        aria-hidden
      />
      <div className="nebula pointer-events-none absolute inset-0" aria-hidden />

      <div className="relative z-10 mx-auto flex min-h-screen max-w-[1360px] flex-col gap-5 p-4 md:flex-row md:gap-6 md:p-6">
        <aside className="hud-panel flex w-full shrink-0 flex-col gap-5 p-4 md:w-56">
          <div className="flex items-center gap-3">
            <TwinStarsLogo size={48} />
            <div className="min-w-0">
              <p className="font-display text-sm font-semibold tracking-wide text-frost">
                子言 · 佳琦
              </p>
              <p className="mt-0.5 truncate text-[11px] text-mute">ziyan-mailbus</p>
            </div>
          </div>
          <nav className="flex flex-col gap-0.5" aria-label="主导航">
            {nav}
          </nav>
          <div className="mt-auto border-t border-rail/80 pt-3">
            <p className="hud-label">总线</p>
            <p className="mt-1 animate-pulse-ring text-xs text-mint">在线</p>
          </div>
        </aside>

        <main
          id="main-content"
          tabIndex={-1}
          className="hud-panel relative min-h-[70vh] flex-1 overflow-hidden p-5 md:p-7"
        >
          <div className="animate-panel-rise relative z-10">{children}</div>
        </main>
      </div>
    </div>
  );
}
