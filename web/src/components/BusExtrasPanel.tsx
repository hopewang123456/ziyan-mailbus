/**
 * 总线扩展：路径 / 权限 / A2A — 表单展示（非裸 JSON）
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { ErrorAlert } from "./ErrorAlert";
import { SoftFold } from "./SoftFold";

type PermMap = Record<string, boolean | string | number | null | object>;

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function displayVal(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

export function BusExtrasPanel() {
  const [paths, setPaths] = useState<Record<string, unknown>>({});
  const [perms, setPerms] = useState<PermMap>({});
  const [a2a, setA2a] = useState<Record<string, unknown>>({});
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setErr("");
    const [p, pe, a] = await Promise.all([
      api("/api/settings/paths"),
      api("/api/permission"),
      api("/api/a2a/protocol"),
    ]);
    if (p.ok) setPaths(asRecord(p.data));
    else setErr(p.error);
    if (pe.ok) {
      const raw = asRecord(pe.data);
      const block = (raw.permissions && typeof raw.permissions === "object"
        ? raw.permissions
        : raw) as PermMap;
      setPerms({ ...block });
    }
    if (a.ok) setA2a(asRecord(a.data));
  }

  useEffect(() => {
    void load();
  }, []);

  const pathRows = useMemo(() => {
    const out: { key: string; value: string }[] = [];
    const walk = (obj: Record<string, unknown>, prefix = "") => {
      for (const [k, v] of Object.entries(obj)) {
        if (k === "status" || k === "error") continue;
        const key = prefix ? `${prefix}.${k}` : k;
        if (v && typeof v === "object" && !Array.isArray(v)) walk(v as Record<string, unknown>, key);
        else out.push({ key, value: displayVal(v) });
      }
    };
    walk(paths);
    return out.filter((r) => /root|workspace|dir|path|vault|compose|agent/i.test(r.key));
  }, [paths]);

  const a2aRows = useMemo(() => {
    const out: { key: string; value: string }[] = [];
    const walk = (obj: Record<string, unknown>, prefix = "") => {
      for (const [k, v] of Object.entries(obj)) {
        if (k === "status" || k === "error") continue;
        const key = prefix ? `${prefix}.${k}` : k;
        if (v && typeof v === "object" && !Array.isArray(v)) walk(v as Record<string, unknown>, key);
        else out.push({ key, value: displayVal(v) });
      }
    };
    walk(a2a);
    return out;
  }, [a2a]);

  async function savePerm() {
    setBusy(true);
    setMsg("");
    const r = await api("/api/permission", {
      method: "POST",
      body: JSON.stringify({ permissions: perms }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg("权限已保存");
      void load();
    } else setErr(r.error);
  }

  return (
    <div className="space-y-3">
      <ErrorAlert message={err} />
      {msg ? <p className="text-xs text-mint">{msg}</p> : null}

      <SoftFold title="Vault / Compose 路径" hint="只读 · 运行时解析结果">
        <div className="space-y-2">
          {pathRows.length === 0 ? (
            <p className="text-sm text-mute">加载中…</p>
          ) : (
            pathRows.map((r) => (
              <label key={r.key} className="block soft-inset">
                <span className="text-[11px] font-medium text-frost/80">{r.key}</span>
                <input className="hud-input mt-1 font-mono text-xs" value={r.value} readOnly />
              </label>
            ))
          )}
        </div>
      </SoftFold>

      <SoftFold title="权限" hint="开关表单 · 保存写回 permission.json">
        <div className="mb-2 flex justify-end">
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void savePerm()}>
            保存权限
          </button>
        </div>
        <ul className="grid gap-2 sm:grid-cols-2">
          {Object.keys(perms).length === 0 ? (
            <li className="text-sm text-mute">无权限项</li>
          ) : (
            Object.entries(perms).map(([k, v]) => (
              <li key={k} className="soft-inset flex items-center justify-between gap-2">
                <span className="font-mono text-[11px] text-frost">{k}</span>
                {typeof v === "boolean" ? (
                  <label className="flex items-center gap-1.5 text-[11px] text-mute">
                    <input
                      type="checkbox"
                      checked={v}
                      onChange={(e) => setPerms((m) => ({ ...m, [k]: e.target.checked }))}
                    />
                    {v ? "允许" : "禁止"}
                  </label>
                ) : (
                  <input
                    className="hud-input max-w-[14rem] font-mono text-xs"
                    value={displayVal(v)}
                    onChange={(e) => setPerms((m) => ({ ...m, [k]: e.target.value }))}
                  />
                )}
              </li>
            ))
          )}
        </ul>
      </SoftFold>

      <SoftFold title="A2A 协议" hint="只读摘要">
        <div className="space-y-2">
          {a2aRows.length === 0 ? (
            <p className="text-sm text-mute">加载中…</p>
          ) : (
            a2aRows.map((r) => (
              <label key={r.key} className="block soft-inset">
                <span className="text-[11px] font-medium text-frost/80">{r.key}</span>
                {r.value.length > 80 || r.value.startsWith("{") || r.value.startsWith("[") ? (
                  <textarea
                    className="hud-input mt-1 min-h-[4.5rem] w-full font-mono text-xs"
                    value={r.value}
                    readOnly
                  />
                ) : (
                  <input className="hud-input mt-1 font-mono text-xs" value={r.value} readOnly />
                )}
              </label>
            ))
          )}
        </div>
      </SoftFold>
    </div>
  );
}
