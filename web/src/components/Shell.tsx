import type { ReactNode } from "react";

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
        className="starfield pointer-events-none absolute inset-0 animate-star-drift opacity-70"
        aria-hidden
      />
      <div className="nebula pointer-events-none absolute inset-0" aria-hidden />

      <div className="relative z-10 mx-auto flex min-h-screen max-w-[1400px] flex-col gap-4 p-4 md:flex-row md:p-6">
        <aside className="hud-panel flex w-full shrink-0 flex-col gap-4 p-4 md:w-56">
          <div>
            <p className="hud-label">Vessel</p>
            <p className="mt-1 font-display text-sm tracking-[0.18em] text-cyan-signal">
              ziyan-mailbus
            </p>
            <p className="mt-1 text-xs text-mute">Cockpit · Wave D</p>
          </div>
          <nav className="flex flex-col gap-1" aria-label="主导航">
            {nav}
          </nav>
          <div className="mt-auto border-t border-rail pt-3">
            <p className="hud-label">回退</p>
            <a
              href="/legacy/"
              className="mt-2 block text-xs text-mute underline-offset-2 hover:text-amber-signal hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-signal"
            >
              旧 HUD（回退）
            </a>
          </div>
        </aside>

        <main
          id="main-content"
          tabIndex={-1}
          className="hud-panel scanline relative min-h-[70vh] flex-1 overflow-hidden p-5 md:p-7"
        >
          <div className="animate-panel-rise relative z-10">{children}</div>
        </main>
      </div>
    </div>
  );
}
