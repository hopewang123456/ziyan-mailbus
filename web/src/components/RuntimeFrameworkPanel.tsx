/**
 * 框架运行时 typed 表单：frameworks + mailbus_codex + mailbus_claude。
 * 保存走 /api/settings/section/<name>；嵌套 map（ports/roots）用行编辑。
 */
import { useEffect, useState } from "react";
import { api, formatSettingsEffects } from "../lib/api";
import { ErrorAlert } from "./ErrorAlert";

type FwEntry = {
  enabled?: boolean;
  mount_mode?: string;
  root_path?: string;
  [k: string]: unknown;
};

type PlatBlock = Record<string, unknown>;

const MOUNT_MODES = ["container", "host", "bind", "none"] as const;
const PLATFORMS = ["auto", "windows", "linux", "wsl", "docker"] as const;

function asObj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

/** GET /api/settings/section/* → 取 data 信封内对象 */
function unwrapSection(body: unknown): Record<string, unknown> {
  const root = asObj(body);
  const inner = root.data;
  if (inner && typeof inner === "object" && !Array.isArray(inner)) return asObj(inner);
  const { status: _s, error: _e, section: _sec, ...rest } = root;
  return rest;
}

function mapToLines(m: unknown): string {
  const o = asObj(m);
  return Object.entries(o)
    .map(([k, v]) => `${k}=${v == null ? "" : String(v)}`)
    .join("\n");
}

function linesToMap(text: string, numeric = false): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const line of text.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#")) continue;
    const i = t.indexOf("=");
    if (i <= 0) continue;
    const k = t.slice(0, i).trim();
    const v = t.slice(i + 1).trim();
    if (!k) continue;
    if (numeric && v !== "" && /^-?\d+$/.test(v)) out[k] = Number(v);
    else out[k] = v;
  }
  return out;
}

export function RuntimeFrameworkPanel() {
  const [frameworks, setFrameworks] = useState<Record<string, FwEntry>>({});
  const [codex, setCodex] = useState<Record<string, unknown>>({});
  const [claude, setClaude] = useState<Record<string, unknown>>({});
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"frameworks" | "codex" | "claude">("frameworks");

  async function load() {
    setErr("");
    const [f, c, cl] = await Promise.all([
      api<{ data?: Record<string, FwEntry> }>("/api/settings/section/frameworks"),
      api<{ data?: Record<string, unknown> }>("/api/settings/section/mailbus_codex"),
      api<{ data?: Record<string, unknown> }>("/api/settings/section/mailbus_claude"),
    ]);
    if (f.ok) setFrameworks(unwrapSection(f.data) as Record<string, FwEntry>);
    else setErr(f.error);
    if (c.ok) setCodex(unwrapSection(c.data));
    else if (!err) setErr(c.error);
    if (cl.ok) setClaude(unwrapSection(cl.data));
    else if (!err) setErr(cl.error);
  }

  useEffect(() => {
    void load();
  }, []);

  function setFw(id: string, patch: Partial<FwEntry>) {
    setFrameworks((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  function setPlat(
    which: "codex" | "claude",
    plat: "windows" | "linux",
    key: string,
    value: unknown,
  ) {
    const setter = which === "codex" ? setCodex : setClaude;
    setter((prev) => {
      const block = { ...asObj(prev[plat]), [key]: value };
      return { ...prev, [plat]: block };
    });
  }

  async function save(section: "frameworks" | "mailbus_codex" | "mailbus_claude") {
    setBusy(true);
    setMsg("");
    setErr("");
    let body: Record<string, unknown>;
    if (section === "frameworks") body = frameworks;
    else if (section === "mailbus_codex") body = codex;
    else body = claude;
    const r = await api(`/api/settings/section/${section}`, {
      method: "POST",
      body: JSON.stringify({ patch: body }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(formatSettingsEffects(r.data, `已保存 ${section}`));
      void load();
    } else setErr(r.error);
  }

  const fwIds = Object.keys(frameworks).sort();
  const codexWin = asObj(codex.windows) as PlatBlock;
  const codexLin = asObj(codex.linux) as PlatBlock;
  const claudeWin = asObj(claude.windows) as PlatBlock;
  const claudeLin = asObj(claude.linux) as PlatBlock;

  return (
    <div className="soft-panel space-y-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="soft-panel-title">框架运行时</p>
          <p className="soft-panel-sub">frameworks · Codex · Claude Code</p>
        </div>
        <div className="flex flex-wrap gap-1">
          {(
            [
              ["frameworks", "框架开关"],
              ["codex", "Codex"],
              ["claude", "Claude"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={tab === id ? "hud-btn hud-btn-primary" : "hud-btn"}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <ErrorAlert message={err} />
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}

      {tab === "frameworks" && (
        <div className="space-y-2">
          <p className="text-xs text-mute">启用 / 挂载模式 / 根路径（空=用实例卡或环境变量）。</p>
          {fwIds.length === 0 && <p className="text-mute">暂无 frameworks 段</p>}
          {fwIds.map((id) => {
            const e = frameworks[id] || {};
            return (
              <div key={id} className="soft-inset grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-end">
                <div>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={e.enabled !== false}
                      onChange={(ev) => setFw(id, { enabled: ev.target.checked })}
                    />
                    <span className="font-mono text-frost">{id}</span>
                  </label>
                  <input
                    className="hud-input mt-1 w-full font-mono text-xs"
                    placeholder="root_path"
                    value={String(e.root_path ?? "")}
                    onChange={(ev) => setFw(id, { root_path: ev.target.value })}
                  />
                </div>
                <label className="block">
                  <span className="hud-label">mount_mode</span>
                  <select
                    className="hud-input mt-1 font-mono text-xs"
                    value={String(e.mount_mode || "container")}
                    onChange={(ev) => setFw(id, { mount_mode: ev.target.value })}
                  >
                    {MOUNT_MODES.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                    {e.mount_mode && !(MOUNT_MODES as readonly string[]).includes(String(e.mount_mode)) && (
                      <option value={String(e.mount_mode)}>{String(e.mount_mode)}</option>
                    )}
                  </select>
                </label>
              </div>
            );
          })}
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void save("frameworks")}>
            保存 frameworks
          </button>
        </div>
      )}

      {tab === "codex" && (
        <div className="space-y-3">
          <label className="block max-w-xs">
            <span className="hud-label">platform</span>
            <select
              className="hud-input mt-1 w-full font-mono text-xs"
              value={String(codex.platform || "auto")}
              onChange={(e) => setCodex((p) => ({ ...p, platform: e.target.value }))}
            >
              {PLATFORMS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          {(["windows", "linux"] as const).map((plat) => {
            const block = plat === "windows" ? codexWin : codexLin;
            return (
              <div key={plat} className="soft-inset space-y-2">
                <p className="font-mono text-xs text-frost">{plat}</p>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={Boolean(block.sync_on_launch)}
                    onChange={(e) => setPlat("codex", plat, "sync_on_launch", e.target.checked)}
                  />
                  sync_on_launch
                </label>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={Boolean(block.ensure_gateway_container)}
                    onChange={(e) => setPlat("codex", plat, "ensure_gateway_container", e.target.checked)}
                  />
                  ensure_gateway_container
                </label>
                <label className="block">
                  <span className="hud-label">codex_home</span>
                  <input
                    className="hud-input mt-1 w-full font-mono text-xs"
                    value={String(block.codex_home ?? "")}
                    onChange={(e) => setPlat("codex", plat, "codex_home", e.target.value)}
                  />
                </label>
                <label className="block">
                  <span className="hud-label">default_project_dir</span>
                  <input
                    className="hud-input mt-1 w-full font-mono text-xs"
                    value={String(block.default_project_dir ?? "")}
                    onChange={(e) => setPlat("codex", plat, "default_project_dir", e.target.value)}
                  />
                </label>
              </div>
            );
          })}
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void save("mailbus_codex")}>
            保存 mailbus_codex
          </button>
        </div>
      )}

      {tab === "claude" && (
        <div className="space-y-3">
          <label className="block max-w-xs">
            <span className="hud-label">platform</span>
            <select
              className="hud-input mt-1 w-full font-mono text-xs"
              value={String(claude.platform || "auto")}
              onChange={(e) => setClaude((p) => ({ ...p, platform: e.target.value }))}
            >
              {PLATFORMS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          {(["windows", "linux"] as const).map((plat) => {
            const block = plat === "windows" ? claudeWin : claudeLin;
            return (
              <div key={plat} className="soft-inset space-y-2">
                <p className="font-mono text-xs text-frost">{plat}</p>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={block.enabled !== false}
                    onChange={(e) => setPlat("claude", plat, "enabled", e.target.checked)}
                  />
                  enabled
                </label>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={Boolean(block.ensure_on_launch)}
                    onChange={(e) => setPlat("claude", plat, "ensure_on_launch", e.target.checked)}
                  />
                  ensure_on_launch
                </label>
                {(
                  [
                    ["claude_home", "claude_home"],
                    ["claude_bin", "claude_bin"],
                    ["ttyd_bin", "ttyd_bin"],
                    ["default_project_dir", "default_project_dir"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key} className="block">
                    <span className="hud-label">{label}</span>
                    <input
                      className="hud-input mt-1 w-full font-mono text-xs"
                      value={String(block[key] ?? "")}
                      onChange={(e) => setPlat("claude", plat, key, e.target.value)}
                    />
                  </label>
                ))}
                <label className="block">
                  <span className="hud-label">browser_ports（每行 agent=端口）</span>
                  <textarea
                    className="hud-input mt-1 min-h-[72px] w-full font-mono text-xs"
                    value={mapToLines(block.browser_ports)}
                    onChange={(e) => setPlat("claude", plat, "browser_ports", linesToMap(e.target.value, true))}
                  />
                </label>
                <label className="block">
                  <span className="hud-label">default_project_roots（每行 agent=路径）</span>
                  <textarea
                    className="hud-input mt-1 min-h-[72px] w-full font-mono text-xs"
                    value={mapToLines(block.default_project_roots)}
                    onChange={(e) =>
                      setPlat("claude", plat, "default_project_roots", linesToMap(e.target.value, false))
                    }
                  />
                </label>
              </div>
            );
          })}
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void save("mailbus_claude")}>
            保存 mailbus_claude
          </button>
        </div>
      )}
    </div>
  );
}
