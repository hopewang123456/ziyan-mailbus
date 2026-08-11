import { useEffect, useMemo, useState } from "react";
import { ErrorAlert } from "../components/ErrorAlert";
import { api } from "../lib/api";

type ReviewReport = {
  file: string;
  repo?: string;
  time?: string;
  size?: number;
  content?: string;
};

type ReviewDetail = {
  file?: string;
  html?: string;
  raw?: string;
};

export function ReviewsPage() {
  const [reports, setReports] = useState<ReviewReport[]>([]);
  const [projects, setProjects] = useState<Record<string, { file: string; time?: string }[]>>({});
  const [filterRepo, setFilterRepo] = useState("");
  const [selected, setSelected] = useState<string>("");
  const [preview, setPreview] = useState<ReviewDetail | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    void Promise.all([
      api<{ reports?: ReviewReport[] }>("/api/reviews"),
      api<{ projects?: Record<string, { file: string; time?: string }[]> }>("/api/reviews/projects"),
    ]).then(([a, b]) => {
      if (a.ok) setReports(Array.isArray(a.data.reports) ? a.data.reports : []);
      else setErr(a.error);
      if (b.ok && b.data.projects) setProjects(b.data.projects);
    });
  }, []);

  const repoOptions = useMemo(() => {
    const fromProjects = Object.keys(projects);
    const fromReports = reports.map((r) => r.repo).filter(Boolean) as string[];
    return [...new Set([...fromProjects, ...fromReports])].sort();
  }, [projects, reports]);

  const filtered = useMemo(() => {
    if (!filterRepo) return reports;
    return reports.filter((r) => r.repo === filterRepo);
  }, [reports, filterRepo]);

  async function selectReport(file: string, inline?: string) {
    setSelected(file);
    setPreview(null);
    if (inline) {
      setPreview({ file, raw: inline });
      return;
    }
    const r = await api<ReviewDetail>(`/api/reviews/${encodeURIComponent(file)}`);
    if (r.ok) setPreview(r.data);
    else setErr(r.error);
  }

  return (
    <div className="space-y-4">
      <header>
        <p className="hud-label">Sensor logs</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide">Reviews</h2>
      </header>
      <ErrorAlert message={err} />

      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="hud-label">Project filter</span>
          <select
            className="hud-input mt-1 min-w-40"
            value={filterRepo}
            onChange={(e) => setFilterRepo(e.target.value)}
          >
            <option value="">全部</option>
            {repoOptions.map((repo) => (
              <option key={repo} value={repo}>
                {repo}
              </option>
            ))}
          </select>
        </label>
        <span className="text-xs text-mute">{filtered.length} reports</span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="hud-panel p-4">
          <p className="hud-label">Reports</p>
          {filtered.length === 0 ? (
            <p className="mt-2 text-sm text-mute">无报告</p>
          ) : (
            <ul className="mt-3 max-h-[55vh] space-y-1 overflow-auto">
              {filtered.map((r) => {
                const active = selected === r.file;
                return (
                  <li key={r.file}>
                    <button
                      type="button"
                      className={`w-full border-b border-rail/50 px-1 py-2 text-left text-xs transition-colors ${
                        active ? "bg-[rgba(61,224,255,0.1)] text-frost" : "text-mute hover:text-frost"
                      }`}
                      onClick={() => void selectReport(r.file, r.content)}
                    >
                      <span className="font-mono">{r.file}</span>
                      {r.repo && <span className="ml-2 text-cyan-signal">{r.repo}</span>}
                      {r.time && <p className="mt-0.5 text-mute">{r.time}</p>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="hud-panel p-4">
          <p className="hud-label">Preview</p>
          {!selected ? (
            <p className="mt-2 text-sm text-mute">选择报告预览</p>
          ) : !preview ? (
            <p className="mt-2 text-sm text-mute">加载中…</p>
          ) : preview.html ? (
            <div
              className="prose-invert mt-3 max-h-[55vh] overflow-auto text-xs text-mute"
              dangerouslySetInnerHTML={{ __html: preview.html }}
            />
          ) : (
            <pre className="mt-3 max-h-[55vh] overflow-auto whitespace-pre-wrap text-xs text-mute">
              {preview.raw || ""}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
