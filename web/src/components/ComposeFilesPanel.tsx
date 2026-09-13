/**
 * Compose YAML 文件柜：列表 / 加载 / 保存。不含 docker compose 启停。
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorAlert } from "./ErrorAlert";

type FileRow = { path?: string; name?: string; size?: number };

export function ComposeFilesPanel() {
  const [files, setFiles] = useState<FileRow[]>([]);
  const [active, setActive] = useState("");
  const [content, setContent] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(async () => {
    setErr("");
    const r = await api<{ files?: FileRow[]; note?: string }>("/api/settings/compose-files");
    if (!r.ok) {
      setErr(r.error || "list failed");
      return;
    }
    setFiles(r.data.files || []);
    if (r.data.note) setMsg(r.data.note);
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  async function openFile(path: string) {
    setErr("");
    setBusy(true);
    const r = await api<{ content?: string }>(`/api/settings/compose-files/${encodeURIComponent(path)}`);
    setBusy(false);
    if (!r.ok) {
      setErr(r.error || "read failed");
      return;
    }
    setActive(path);
    setContent(String(r.data.content || ""));
  }

  async function save() {
    if (!active) return;
    setBusy(true);
    setErr("");
    const r = await api(`/api/settings/compose-files/${encodeURIComponent(active)}`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    setBusy(false);
    if (!r.ok) {
      setErr(r.error || "save failed");
      return;
    }
    setMsg(`已保存 ${active}（启停请用运维侧 docker compose / k8s）`);
    void loadList();
  }

  return (
    <div className="space-y-3">
      <p className="text-sm opacity-80">
        加载并编辑仓库内 compose YAML；<strong>不会</strong>执行 up/down。
      </p>
      {err ? <ErrorAlert message={err} /> : null}
      {msg ? <p className="text-xs opacity-70">{msg}</p> : null}
      <ul className="text-sm space-y-1 max-h-40 overflow-auto">
        {files.map((f) => {
          const p = String(f.path || "");
          return (
            <li key={p}>
              <button
                type="button"
                className={`underline ${active === p ? "font-semibold" : ""}`}
                disabled={busy}
                onClick={() => void openFile(p)}
              >
                {p}
              </button>
            </li>
          );
        })}
        {!files.length ? <li className="opacity-60">暂无 docker-compose*.yml</li> : null}
      </ul>
      {active ? (
        <>
          <textarea
            className="w-full min-h-[220px] font-mono text-xs p-2 border rounded"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={busy}
          />
          <button type="button" className="px-3 py-1 border rounded" disabled={busy} onClick={() => void save()}>
            保存 YAML
          </button>
        </>
      ) : null}
    </div>
  );
}
