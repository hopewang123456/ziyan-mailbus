import { useEffect, useState } from "react";
import { ErrorAlert } from "../../components/ErrorAlert";
import { api } from "../../lib/api";

/** Thin L3 list page: GET path and render JSON / array under listKey. */
export function ApiListPage({
  title,
  path,
  listKey,
}: {
  title: string;
  path: string;
  listKey?: string;
}) {
  const [data, setData] = useState<unknown>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setErr("");
      const r = await api(path);
      if (cancelled) return;
      if (r.ok) setData(r.data);
      else setErr(r.error);
    })();
    return () => {
      cancelled = true;
    };
  }, [path]);

  const list =
    listKey && data && typeof data === "object" && data !== null
      ? (data as Record<string, unknown>)[listKey]
      : data;

  return (
    <div className="space-y-3 p-1">
      <header>
        <p className="hud-label">Other · API</p>
        <h3 className="font-display text-xl tracking-wide">{title}</h3>
        <p className="mt-1 font-mono text-xs text-mute">{path}</p>
      </header>
      {err ? <ErrorAlert message={err} /> : null}
      <pre className="max-h-[50vh] overflow-auto rounded-sm border border-rail bg-hull/50 p-3 text-xs">
        {list == null ? "…" : JSON.stringify(list, null, 2)}
      </pre>
    </div>
  );
}
