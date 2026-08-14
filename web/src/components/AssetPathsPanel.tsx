import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorAlert } from "./ErrorAlert";

/**
 * 资产路径（28b）— mailbus 自身 skills / rules / identity 三项。
 * 默认 = 仓库内 junction 路径（skills|rules|identities）；自定义 = Obsidian Vault 目录。
 * 保存走 /api/settings/section/asset_paths（后端写 .env，default 删除键）。
 */

type AssetItem = {
  key: string;
  label: string;
  env: string;
  default: string;
  effective: string;
  mode: string;
  custom: string;
  vault: string;
  hint: string;
  exists: boolean;
};

type AssetResp = {
  status?: string;
  data?: { items?: AssetItem[] };
  note?: string;
};

export function AssetPathsPanel() {
  const [items, setItems] = useState<AssetItem[]>([]);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setErr("");
    const r = await api<AssetResp>("/api/settings/section/asset_paths");
    setBusy(false);
    if (r.ok) {
      setItems(r.data?.data?.items ?? []);
      setNote(r.data?.note ?? "");
    } else setErr(r.error);
  }

  useEffect(() => {
    void load();
  }, []);

  function setMode(key: string, mode: "default" | "custom") {
    setItems((prev) => prev.map((it) => (it.key === key ? { ...it, mode } : it)));
  }
  function setCustom(key: string, v: string) {
    setItems((prev) => prev.map((it) => (it.key === key ? { ...it, custom: v } : it)));
  }

  async function save() {
    setBusy(true);
    setMsg("");
    setErr("");
    const r = await api<{ updated?: string[] }>("/api/settings/section/asset_paths", {
      method: "POST",
      body: JSON.stringify({ patch: { items } }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(`已保存（需重启生效）: ${(r.data.updated || []).join(", ")}`);
      void load();
    } else setErr(r.error);
  }

  return (
    <div className="soft-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="soft-panel-title">资产路径</p>
          <p className="soft-panel-sub">skill / rule / identity</p>
        </div>
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void save()}>
          保存
        </button>
      </div>
      <p className="mt-3 text-[13px] leading-relaxed text-mute">
        默认 = 仓库内 junction；自定义 = Obsidian Vault 目录，写入 .env。
        <span className="text-amber-signal"> 需重启 mailbus 生效。</span>
      </p>
      {err && <ErrorAlert message={err} />}
      {msg && <p className="mt-2 text-xs text-frost">{msg}</p>}
      {note && <p className="mt-2 text-[10px] text-mute">{note}</p>}
      <div className="mt-3 space-y-3">
        {items.map((it) => (
          <div key={it.key} className="soft-inset">
            <div className="flex flex-wrap items-center gap-3">
              <span className="w-20 text-sm font-medium text-frost">{it.label}</span>
              <label className="flex items-center gap-1 text-xs text-mute">
                <input
                  type="radio"
                  name={`mode-${it.key}`}
                  checked={it.mode === "default"}
                  onChange={() => setMode(it.key, "default")}
                />
                默认
              </label>
              <label className="flex items-center gap-1 text-xs text-mute">
                <input
                  type="radio"
                  name={`mode-${it.key}`}
                  checked={it.mode === "custom"}
                  onChange={() => setMode(it.key, "custom")}
                />
                自定义
              </label>
              <span className="agent-chip">{it.env}</span>
              {it.exists ? (
                <span className="agent-chip agent-chip-live">存在</span>
              ) : (
                <span className="agent-chip agent-chip-warn">不存在</span>
              )}
            </div>
            {it.mode === "default" ? (
              <p className="mt-2 break-all font-mono text-[10px] text-mute">{it.default}</p>
            ) : (
              <input
                className="hud-input mt-2 font-mono text-xs"
                value={it.custom}
                placeholder={it.vault}
                onChange={(e) => setCustom(it.key, e.target.value)}
              />
            )}
            <p className="mt-1 text-[10px] text-mute">{it.hint}</p>
          </div>
        ))}
        {items.length === 0 && <p className="text-xs text-mute">加载中…</p>}
      </div>
    </div>
  );
}
