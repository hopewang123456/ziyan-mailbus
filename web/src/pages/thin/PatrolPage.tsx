import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ErrorAlert } from "../../components/ErrorAlert";
import { t } from "../../lib/i18n";

type Report = {
  file?: string;
  date?: string;
  summary?: string;
  content?: string;
};

export function PatrolPage() {
  const [items, setItems] = useState<Report[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<Report | null>(null);

  async function load() {
    setBusy(true);
    const r = await api<{ reports?: Report[] }>("/api/patrol-reports");
    setBusy(false);
    if (r.ok) setItems(Array.isArray(r.data.reports) ? r.data.reports : []);
    else setErr(r.error);
  }

  useEffect(() => {
    void load();
  }, []);

  async function archive(file: string) {
    if (!window.confirm(`归档 ${file}？`)) return;
    setBusy(true);
    const r = await api(`/api/patrol-reports/${encodeURIComponent(file)}/archive`, {
      method: "POST",
      body: "{}",
    });
    setBusy(false);
    if (!r.ok) setErr(r.error);
    if (open?.file === file) setOpen(null);
    void load();
  }

  return (
    <div className="space-y-3">
      <header>
        <p className="hud-label">{t("patrol")}</p>
        <h2 className="mt-1 font-display text-xl">巡检报告</h2>
      </header>
      <ErrorAlert message={err} />
      <button type="button" className="hud-btn" disabled={busy} onClick={() => void load()}>
        刷新
      </button>
      <ul className="space-y-2">
        {items.map((r) => (
          <li key={r.file} className="hud-panel p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setOpen(r)}>
                <p className="font-mono text-xs text-cyan-signal">{r.file}</p>
                <p className="mt-1 text-xs text-mute">{r.date}</p>
                <p className="mt-1 line-clamp-2 text-sm text-frost/85">{r.summary}</p>
              </button>
              {r.file ? (
                <button
                  type="button"
                  className="hud-btn shrink-0"
                  disabled={busy}
                  onClick={() => void archive(r.file!)}
                >
                  归档
                </button>
              ) : null}
            </div>
          </li>
        ))}
        {!items.length && !busy && <li className="text-sm text-mute">暂无巡检报告</li>}
      </ul>
      {open && (
        <div className="hud-panel p-3">
          <div className="mb-2 flex justify-between gap-2">
            <p className="font-mono text-xs text-cyan-signal">{open.file}</p>
            <button type="button" className="hud-btn text-xs" onClick={() => setOpen(null)}>
              关闭预览
            </button>
          </div>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap text-xs text-mute">{open.content}</pre>
        </div>
      )}
    </div>
  );
}
