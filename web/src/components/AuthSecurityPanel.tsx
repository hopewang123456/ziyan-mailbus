/**
 * 鉴权设置：无 Token 写开关 + CIDR + CORS Origins（表单，非裸 JSON）。
 */
import { useEffect, useState } from "react";
import { api, formatSettingsEffects } from "../lib/api";
import { ErrorAlert } from "./ErrorAlert";

const PRESETS = [
  { label: "本机 IPv4", cidr: "127.0.0.1/32" },
  { label: "本机 IPv6", cidr: "::1/128" },
  { label: "Docker/WSL 桥", cidr: "172.16.0.0/12" },
  { label: "私网 192.168", cidr: "192.168.0.0/16" },
];

export function AuthSecurityPanel() {
  const [enabled, setEnabled] = useState(false);
  const [cidrs, setCidrs] = useState("");
  const [cors, setCors] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setErr("");
    const r = await api<{ data?: Record<string, unknown> }>("/api/settings/section/auth");
    if (!r.ok) {
      setErr(r.error || "load failed");
      return;
    }
    const d = (r.data.data || {}) as Record<string, unknown>;
    setEnabled(Boolean(d.allow_write_without_token));
    const c = d.write_without_token_cidrs || d.exempt_cidrs || [];
    setCidrs(Array.isArray(c) ? c.join("\n") : String(c || ""));
    const o = d.cors_origins || [];
    setCors(Array.isArray(o) ? o.join("\n") : String(o || ""));
  }

  useEffect(() => {
    void load();
  }, []);

  function addPreset(cidr: string) {
    const lines = cidrs.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
    if (!lines.includes(cidr)) setCidrs([...lines, cidr].join("\n"));
  }

  async function save() {
    setBusy(true);
    setErr("");
    setMsg("");
    const write_without_token_cidrs = cidrs
      .split(/\r?\n/)
      .map((x) => x.trim())
      .filter(Boolean);
    const cors_origins = cors
      .split(/\r?\n/)
      .map((x) => x.trim())
      .filter(Boolean);
    const r = await api("/api/settings/section/auth", {
      method: "POST",
      body: JSON.stringify({
        allow_write_without_token: enabled,
        write_without_token_cidrs,
        cors_origins,
      }),
    });
    setBusy(false);
    if (!r.ok) {
      setErr(r.error || "save failed");
      return;
    }
    setMsg(formatSettingsEffects(r.data, "已保存（鉴权变更建议重启 mailbus serve）"));
    void load();
  }

  return (
    <div className="space-y-3 text-sm">
      <p className="opacity-80">
        默认所有写 API 需要 Token。开启后仅下列 CIDR 可无 Token 写（含 WSL/虚拟机）。CORS 默认不放行
        <code className="mx-1">*</code>；需要跨域时填写 Origin 白名单。
      </p>
      {err ? <ErrorAlert message={err} /> : null}
      {msg ? <p className="text-xs text-mute">{msg}</p> : null}
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} disabled={busy} />
        允许白名单网段无 Token 写入
      </label>
      <div>
        <div className="mb-1 opacity-70">write_without_token_cidrs</div>
        <div className="flex flex-wrap gap-2 mb-2">
          {PRESETS.map((p) => (
            <button key={p.cidr} type="button" className="px-2 py-0.5 border rounded text-xs" onClick={() => addPreset(p.cidr)}>
              + {p.label}
            </button>
          ))}
        </div>
        <textarea
          className="w-full min-h-[88px] font-mono text-xs p-2 border rounded"
          value={cidrs}
          onChange={(e) => setCidrs(e.target.value)}
          placeholder={"127.0.0.1/32\n172.16.0.0/12"}
          disabled={busy}
        />
      </div>
      <div>
        <div className="mb-1 opacity-70">cors_origins（每行一个；可写 *）</div>
        <textarea
          className="w-full min-h-[64px] font-mono text-xs p-2 border rounded"
          value={cors}
          onChange={(e) => setCors(e.target.value)}
          placeholder={"http://localhost:5173"}
          disabled={busy}
        />
      </div>
      <button type="button" className="px-3 py-1 border rounded" disabled={busy} onClick={() => void save()}>
        保存鉴权
      </button>
    </div>
  );
}
