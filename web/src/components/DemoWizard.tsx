import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAlert } from "./ErrorAlert";
import { api } from "../lib/api";
import { getLang, setLang, t, type Lang } from "../lib/i18n";

type StatsResp = { agent_count?: number };
type TraceResp = { active?: boolean; task_id?: string; lines?: string[] };
type RunResp = { ok?: boolean; task_id?: string; task_status?: string; lines?: string[] };

/**
 * E-wizard 首次启动向导：空 store（无 agent）时引导
 * ① 语言 → ② 一键 demo（零依赖完整流转）→ ③ 接入你自己的 agent。
 * 已有 agent 或已完成接入时不出现。
 */
export function DemoWizard() {
  const [hasAgents, setHasAgents] = useState<boolean | null>(null);
  const [trace, setTrace] = useState<TraceResp | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [taskId, setTaskId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [lang, setLangState] = useState<Lang>(getLang());

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [sR, tR] = await Promise.all([
        api<StatsResp>("/api/stats"),
        api<TraceResp>("/api/demo/trace"),
      ]);
      if (cancelled) return;
      if (sR.ok) setHasAgents((sR.data.agent_count ?? 0) > 0);
      if (tR.ok) {
        setTrace(tR.data);
        setLines(tR.data.lines || []);
        setTaskId(tR.data.task_id || "");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (hasAgents !== false) return null; // 只在空 store 首次启动出现

  function toggleLang() {
    const next: Lang = lang === "zh" ? "en" : "zh";
    setLang(next);
    setLangState(next);
    window.dispatchEvent(new Event("mailbus:lang"));
  }

  async function runDemo() {
    setBusy(true);
    setErr("");
    const r = await api<RunResp>("/api/demo/run", {
      method: "POST",
      body: JSON.stringify({}),
    });
    setBusy(false);
    if (!r.ok) {
      setErr(r.error);
      return;
    }
    setLines(r.data?.lines || []);
    setTaskId(r.data?.task_id || "");
  }

  return (
    <div className="soft-panel space-y-3 px-4 py-3" data-surface="onboarding">
      <header>
        <p className="hud-label">First Run</p>
        <h3 className="mt-1 font-display text-lg text-frost">欢迎使用 mailbus — 3 步看到第一条工单</h3>
        <p className="mt-1 text-[12px] text-mute">零框架安装、零 API key；演示数据独立隔离，随时清除。</p>
      </header>
      <ErrorAlert message={err} />

      <div className="grid gap-2 sm:grid-cols-3">
        <div className="soft-inset px-3 py-2">
          <p className="text-[11px] text-mute">① 语言</p>
          <button type="button" className="hud-btn mt-2 !px-3 text-xs" onClick={toggleLang}>
            {lang === "zh" ? "切换 English" : "切换中文"}
          </button>
        </div>
        <div className="soft-inset px-3 py-2">
          <p className="text-[11px] text-mute">② 一键演示</p>
          <button
            type="button"
            className="hud-btn-amber mt-2 !px-3 text-xs"
            disabled={busy}
            onClick={() => void runDemo()}
          >
            {busy ? "演示流转中…" : lines.length ? "再跑一条" : "跑 demo 工单"}
          </button>
          <p className="mt-1 text-[10px] text-mute">建单 → 派工 → 执行 → 回执 → 验收 → 归档</p>
        </div>
        <div className="soft-inset px-3 py-2">
          <p className="text-[11px] text-mute">③ 接入你的 agent</p>
          <Link className="hud-btn mt-2 inline-block !px-3 text-xs" to="/config">
            设置页 · 新建实例卡
          </Link>
          <p className="mt-1 text-[10px] text-mute">填 type/run_target/install_path 后点「测试连接」三段全绿即接好</p>
        </div>
      </div>

      {lines.length > 0 ? (
        <div className="soft-inset px-3 py-2">
          <p className="mb-1 text-[11px] text-mute">
            最近演示{taskId ? ` · ${taskId}` : ""} {trace?.active ? "（演示模式中，可随时清除）" : ""}
          </p>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-frost/90">
            {lines.join("\n")}
          </pre>
        </div>
      ) : (
        <p className="text-[11px] text-mute">还没跑过演示——点上方「跑 demo 工单」，几秒内看到完整流转。CLI 等价：mailbus demo</p>
      )}
      <p className="text-[10px] text-mute">{t("lang")} · Wizard v1（E-wizard 最小版）</p>
    </div>
  );
}
