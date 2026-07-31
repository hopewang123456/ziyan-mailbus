import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

export function HomePage() {
  const [status, setStatus] = useState<string>("…");

  useEffect(() => {
    void api<{ version?: string; status?: string }>("/api/status").then((r) => {
      if (r.ok) {
        const d = r.data as Record<string, unknown>;
        setStatus(String(d.version || d.status || "online"));
      } else {
        setStatus(r.error);
      }
    });
  }, []);

  return (
    <section className="relative flex min-h-[60vh] flex-col justify-center">
      <p className="hud-label mb-4">Starship bridge</p>
      {/* Motion #2: brand entrance */}
      <h1 className="animate-brand-in font-display text-4xl font-bold uppercase text-frost md:text-6xl">
        ziyan-mailbus
      </h1>
      <p className="mt-4 max-w-xl text-base text-mute md:text-lg">
        星系驾驶舱 · 编排总线与 agent 舰队的实时视界。非管理台，是舰桥。
      </p>

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center gap-2 rounded-sm border border-mint/30 bg-mint/10 px-3 py-1.5 text-xs text-mint">
          <span className="h-2 w-2 animate-pulse-ring rounded-full bg-mint" />
          bus {status}
        </span>
        <Link to="/config" className="hud-btn">
          配置 / Token
        </Link>
        <Link to="/discover" className="hud-btn-amber">
          发现舰队
        </Link>
      </div>

      <div className="mt-12 grid gap-3 sm:grid-cols-3">
        {[
          ["任务轨", "/tasks", "工单与 FSM"],
          ["Inbox", "/inbox", "信箱与回复"],
          ["诊所", "/clinic", "doctor / tools"],
        ].map(([title, to, sub]) => (
          <Link
            key={to}
            to={to}
            className="group rounded-sm border border-rail bg-hull/60 p-4 transition hover:border-cyan-signal/40 hover:shadow-glow"
          >
            <p className="font-display text-xs tracking-wider text-cyan-signal">{title}</p>
            <p className="mt-1 text-sm text-mute group-hover:text-frost">{sub}</p>
          </Link>
        ))}
      </div>
    </section>
  );
}
