import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { setUiMode } from "../lib/ui-mode";

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
        mailbus
      </h1>
      <p className="mt-4 max-w-xl text-base text-mute md:text-lg">
        逃生舱首页 · 日常请回<strong className="text-frost">舰桥</strong>。此处保留侧栏路由作排障。
      </p>

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center gap-2 rounded-sm border border-mint/30 bg-mint/10 px-3 py-1.5 text-xs text-mint">
          <span className="h-2 w-2 animate-pulse-ring rounded-full bg-mint" />
          bus {status}
        </span>
        <Link to="/" className="hud-btn hud-btn-primary">
          返回舰桥
        </Link>
        <Link to="/config" className="hud-btn">
          配置合页
        </Link>
        <Link
          to="/"
          className="hud-btn-amber"
          onClick={() => setUiMode("cockpit")}
        >
          发现舰队（舰桥）
        </Link>
      </div>

      <div className="mt-12 grid gap-3 sm:grid-cols-3">
        {[
          ["配置合页", "/config", "与舰桥同面板"],
          ["诊所", "/clinic", "doctor / tools"],
          ["协调台", "/manager", "待我处理"],
        ].map(([title, to, sub]) => (
          <Link
            key={to}
            to={to}
            className="group soft-inset transition hover:border-white/15"
          >
            <p className="font-display text-xs tracking-wider text-cyan-signal">{title}</p>
            <p className="mt-1 text-sm text-mute group-hover:text-frost">{sub}</p>
          </Link>
        ))}
      </div>
      <p className="mt-6 text-xs text-mute">任务 / Inbox / 发现等请回舰桥旋钮操作；旧直链已自动跳转。</p>
    </section>
  );
}
