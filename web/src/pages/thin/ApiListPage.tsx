import { useEffect, useState } from "react";
import { ErrorAlert } from "../../components/ErrorAlert";
import { api } from "../../lib/api";

type Variant = "form" | "mail" | "stats";

/** Thin L3 list page — form / 邮件展板 / 统计卡 */
export function ApiListPage({
  title,
  path,
  listKey,
  variant = "form",
}: {
  title: string;
  path: string;
  listKey?: string;
  variant?: Variant;
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
        <p className="soft-panel-title">{title}</p>
        <p className="soft-panel-sub font-mono text-[11px]">{path}</p>
      </header>
      {err ? <ErrorAlert message={err} /> : null}
      {variant === "mail" ? (
        <MailBoardView value={list} />
      ) : variant === "stats" ? (
        <StatsBoardView value={list ?? data} />
      ) : (
        <FormishView value={list} />
      )}
    </div>
  );
}

function asRec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function pickStr(row: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = row[k];
    if (typeof v === "string" && v.trim()) return v;
    if (typeof v === "number" || typeof v === "boolean") return String(v);
  }
  return "";
}

function displayVal(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

/** 公告 / 告警：每条一封邮件展板 */
function MailBoardView({ value }: { value: unknown }) {
  if (value == null) return <p className="text-sm text-mute">加载中…</p>;
  const rows = Array.isArray(value)
    ? value
    : typeof value === "object"
      ? Object.entries(value as Record<string, unknown>).map(([k, v]) =>
          typeof v === "object" && v ? { id: k, ...(v as object) } : { id: k, body: v },
        )
      : [];
  if (rows.length === 0) return <p className="text-sm text-mute">暂无条目</p>;

  return (
    <ul className="space-y-3">
      {rows.map((raw, i) => {
        const row = asRec(raw);
        const subject =
          pickStr(row, ["subject", "title", "summary", "message", "name", "id"]) || `条目 ${i + 1}`;
        const from = pickStr(row, ["from", "sender", "source", "agent", "level", "severity"]);
        const when = pickStr(row, ["created_at", "ts", "time", "at", "updated_at", "date"]);
        const body =
          pickStr(row, ["body", "content", "text", "detail", "description", "message"]) ||
          Object.entries(row)
            .filter(([k]) => !["subject", "title", "from", "sender", "created_at", "ts", "id"].includes(k))
            .slice(0, 8)
            .map(([k, v]) => `${k}: ${displayVal(v)}`)
            .join("\n");
        return (
          <li key={String(row.id || i)} className="mail-board">
            <header className="mail-board-head">
              <p className="mail-board-subject">{subject}</p>
              <div className="mail-board-meta">
                {from ? <span>{from}</span> : null}
                {when ? <span>{when}</span> : null}
              </div>
            </header>
            <pre className="mail-board-body">{body}</pre>
          </li>
        );
      })}
    </ul>
  );
}

/** 统计：数字卡网格，非表单 */
function StatsBoardView({ value }: { value: unknown }) {
  if (value == null) return <p className="text-sm text-mute">加载中…</p>;
  const rec = asRec(value);
  const entries: { label: string; value: string }[] = [];

  const walk = (obj: Record<string, unknown>, prefix = "") => {
    for (const [k, v] of Object.entries(obj)) {
      if (k === "status" || k === "error") continue;
      const label = prefix ? `${prefix}.${k}` : k;
      if (v && typeof v === "object" && !Array.isArray(v)) walk(v as Record<string, unknown>, label);
      else if (Array.isArray(v)) entries.push({ label, value: `${v.length} 项` });
      else entries.push({ label, value: displayVal(v) });
    }
  };
  walk(rec);

  if (entries.length === 0) return <p className="text-sm text-mute">暂无统计</p>;

  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {entries.map((e) => (
        <li key={e.label} className="stats-tile">
          <p className="stats-tile-label">{e.label}</p>
          <p className="stats-tile-value">{e.value}</p>
        </li>
      ))}
    </ul>
  );
}

function FormishView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null) return <p className="text-sm text-mute">{depth === 0 ? "加载中…" : "—"}</p>;

  if (Array.isArray(value)) {
    if (value.length === 0) return <p className="text-sm text-mute">空列表</p>;
    return (
      <ul className="space-y-2">
        {value.map((item, i) => (
          <li key={i} className="soft-inset">
            {item && typeof item === "object" ? (
              <FormishView value={item} depth={depth + 1} />
            ) : (
              <span className="font-mono text-xs">{String(item)}</span>
            )}
          </li>
        ))}
      </ul>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([k]) => k !== "status" && k !== "error",
    );
    return (
      <div className="space-y-2">
        {entries.map(([k, v]) => (
          <div key={k} className="soft-inset">
            <span className="text-[11px] font-medium text-frost/80">{k}</span>
            {v && typeof v === "object" ? (
              <div className="mt-1.5 border-l border-white/10 pl-2">
                <FormishView value={v} depth={depth + 1} />
              </div>
            ) : (
              <input className="hud-input mt-1 font-mono text-xs" readOnly value={v == null ? "" : String(v)} />
            )}
          </div>
        ))}
      </div>
    );
  }

  return <p className="soft-inset font-mono text-xs">{String(value)}</p>;
}
