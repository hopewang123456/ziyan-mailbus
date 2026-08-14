import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  agentFrameworkLabel,
  matchesOrbitFilter,
  type AgentRow,
  type OrbitFilter,
} from "../lib/agents";
import { PortraitHud } from "./PortraitHud";
import { HudL3Modal } from "./HudL3Modal";
import { getLang, t } from "../lib/i18n";
import { api } from "../lib/api";

const AGENTS_TTL_MS = 8000;
const MANIFEST_POLL_MS = 1200;
const ORBIT_FILTERS: OrbitFilter[] = [
  "all",
  "hermes",
  "openclaw",
  "opencode",
  "codex",
  "claude",
];
let agentsCache: { at: number; rows: AgentRow[] } | null = null;

function portraitPath(id: string) {
  return `/api/agent-avatar/${encodeURIComponent(id)}/portrait`;
}

type AgentsResp = { agents?: Record<string, Partial<AgentRow>> | AgentRow[] };

function toRows(raw: AgentsResp["agents"]): AgentRow[] {
  const dict: Record<string, Partial<AgentRow>> = Array.isArray(raw)
    ? Object.fromEntries(
        (raw as Array<Partial<AgentRow> & { id?: string }>).map((row, i) => [
          String(row.id || `agent-${i}`),
          row,
        ]),
      )
    : ((raw || {}) as Record<string, Partial<AgentRow>>);
  const rows: AgentRow[] = Object.entries(dict).map(([id, cfg]) => ({
    id,
    ...cfg,
    launch_modes: cfg.launch_modes || ["cli"],
  }));
  rows.sort((x, y) => x.id.localeCompare(y.id));
  return rows;
}

/** 齐套门禁：全部 agent 静+动均存在才上环 */
export function AgentOrbitPanel() {
  const [roster, setRoster] = useState<AgentRow[]>([]);
  const [err, setErr] = useState("");
  const [ready, setReady] = useState(false);
  const [checking, setChecking] = useState(true);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<AgentRow | null>(null);
  const [launchingMode, setLaunchingMode] = useState<"browser" | "cli" | "client" | null>(null);
  const [launchMsg, setLaunchMsg] = useState("");
  const [launchErr, setLaunchErr] = useState("");
  const [manifest, setManifest] = useState<{ complete?: boolean; count?: number } | null>(null);
  const [manifestPending, setManifestPending] = useState(true);
  const [filter, setFilter] = useState<OrbitFilter>("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement>(null);
  const [, langTick] = useState(() => getLang());
  const rosterRef = useRef<AgentRow[]>([]);
  rosterRef.current = roster;

  useEffect(() => {
    const onLang = () => langTick(getLang());
    window.addEventListener("mailbus:lang", onLang);
    return () => window.removeEventListener("mailbus:lang", onLang);
  }, []);

  useEffect(() => {
    if (!filterOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (!filterRef.current?.contains(e.target as Node)) setFilterOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFilterOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      window.removeEventListener("keydown", onKey);
    };
  }, [filterOpen]);

  const filterLabel = filter === "all" ? t("orbitFilterAll") : filter;

  const loadRoster = useCallback(async (force = false) => {
    setErr("");
    setLoading(true);
    if (!force && agentsCache && Date.now() - agentsCache.at < AGENTS_TTL_MS) {
      setRoster(agentsCache.rows);
      rosterRef.current = agentsCache.rows;
      setLoading(false);
      return agentsCache.rows.length;
    }
    try {
      const [agentsRes, launchRes] = await Promise.all([
        api<AgentsResp & { error?: string; message?: string }>(`/api/agents?_=${Date.now()}`),
        api<{ agents?: Record<string, Partial<AgentRow>> }>("/api/launch"),
      ]);
      if (!agentsRes.ok) {
        setErr(agentsRes.error || `HTTP ${agentsRes.status}`);
        setRoster([]);
        return 0;
      }
      const data = agentsRes.data || {};
      let rows = toRows(data.agents);
      const launchMeta = launchRes.ok ? launchRes.data.agents || {} : {};
      rows = rows.map((r) => {
        const lm = launchMeta[r.id] || {};
        return {
          ...r,
          ...lm,
          launch_modes: (lm.launch_modes as string[]) || r.launch_modes || ["cli"],
          has_browser: lm.has_browser ?? r.has_browser,
          has_desktop: lm.has_desktop ?? r.has_desktop,
          launch_url: (lm.launch_url as string) || r.launch_url,
        };
      });
      agentsCache = { at: Date.now(), rows };
      setRoster(rows);
      rosterRef.current = rows;
      if (!rows.length) setErr("agents 列表为空");
      return rows.length;
    } catch (e) {
      try {
        const sr = await api<{ agent_statuses?: Record<string, { type?: string }> }>(
          `/api/status?_=${Date.now()}`,
        );
        const statuses = (sr.ok ? sr.data?.agent_statuses : {}) || {};
        const rows: AgentRow[] = Object.keys(statuses).map((id) => ({
          id,
          name: id,
          role: "",
          type: statuses[id]?.type || "?",
          launch_modes: ["cli"],
        }));
        rows.sort((x, y) => x.id.localeCompare(y.id));
        if (rows.length) {
          setRoster(rows);
          rosterRef.current = rows;
          setErr("agents 慢/超时，已用 status 名册降级");
          return rows.length;
        }
      } catch {
        /* ignore */
      }
      setErr(e instanceof Error ? e.message : String(e));
      setRoster([]);
      return 0;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      for (let i = 0; i < 8 && alive; i++) {
        const n = await loadRoster(i === 0);
        if (n > 0 || rosterRef.current.length > 0) break;
        await new Promise((r) => window.setTimeout(r, 500));
      }
    })();
    return () => {
      alive = false;
    };
  }, [loadRoster]);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;

    async function poll() {
      const r = await api<{ complete?: boolean; count?: number }>("/api/avatars/manifest");
      if (cancelled) return;
      if (r.ok) {
        setManifest(r.data);
        setManifestPending(false);
        return;
      }
      timer = window.setTimeout(poll, MANIFEST_POLL_MS);
    }

    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      setChecking(true);
      if (!roster.length) {
        if (!cancelled) {
          setReady(false);
          setChecking(false);
        }
        return;
      }
      // 有名册即可上环：缺肖像的节点用占位，不再被齐套门禁卡住
      if (!cancelled) {
        setReady(true);
        setChecking(false);
      }
      if (manifestPending) return;
      void manifest;
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [roster, manifest, manifestPending]);

  const filtered = useMemo(
    () => roster.filter((ag) => matchesOrbitFilter(ag, filter)),
    [roster, filter],
  );

  const nodes = useMemo(() => {
    const n = Math.max(filtered.length, 1);
    return filtered.map((ag, i) => {
      const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
      return {
        ag,
        left: 50 + Math.cos(ang) * 42,
        top: 50 + Math.sin(ang) * 36,
      };
    });
  }, [filtered]);

  async function launch(id: string, mode: "browser" | "cli" | "client") {
    setLaunchingMode(mode);
    setLaunchMsg("");
    setLaunchErr("");
    const r = await api<{ message?: string; url?: string; hint?: string; detail?: string }>(
      "/api/launch",
      {
        method: "POST",
        body: JSON.stringify({ agent: id, mode: mode === "client" ? "desktop" : mode }),
      },
    );
    if (mode === "browser") {
      if (r.ok) {
        setLaunchMsg(r.data.message || `已启动 ${id}`);
        if (r.data.url) {
          const w = window.open(r.data.url, "_blank", "noopener,noreferrer");
          if (!w) setLaunchMsg((m) => `${m}${t("popupBlocked")}`);
        }
      } else {
        const hint =
          typeof r.data === "object" && r.data && "hint" in r.data
            ? String((r.data as { hint?: string }).hint || "")
            : "";
        setLaunchErr(hint && !r.error.includes(hint) ? `${r.error} · ${hint}` : r.error);
      }
      setLaunchingMode(null);
      return;
    }
    setLaunchingMode(null);
    if (r.ok) {
      setLaunchMsg(r.data.message || `已启动 ${id}`);
    } else {
      const hint =
        typeof r.data === "object" && r.data && "hint" in r.data
          ? String((r.data as { hint?: string }).hint || "")
          : "";
      setLaunchErr(hint && !r.error.includes(hint) ? `${r.error} · ${hint}` : r.error);
    }
  }

  if (!roster.length) {
    return (
      <div className="cp-fleet-loading" data-surface="fleet">
        <div className="cp-fleet-loading-orbit" aria-hidden>
          <span className="cp-fleet-loading-star a" />
          <span className="cp-fleet-loading-star b" />
          <span className="cp-fleet-loading-ring" />
        </div>
        <p className="cp-fleet-loading-title">
          {loading ? t("rosterLoading") : t("rosterEmpty")}
        </p>
        <p className="cp-fleet-loading-hint">
          {loading ? t("rosterSyncHint") : t("rosterRetryHint")}
        </p>
        {err ? <p className="text-xs text-amber-signal">{err}</p> : null}
        {!loading ? (
          <button type="button" className="hud-btn" onClick={() => void loadRoster(true)}>
            {t("refresh")}
          </button>
        ) : null}
      </div>
    );
  }

  // 有名册即展示；不再因头像 manifest / ready 门禁卡住
  void ready;
  void checking;

  return (
    <div className="cp-orbit-panel" data-surface="fleet">
      <div className="cp-orbit-filter" ref={filterRef} role="group" aria-label={t("agents")}>
        <span className="cp-orbit-filter-label">{t("agents")}</span>
        <div className="cp-orbit-dd">
          <button
            type="button"
            id="cp-orbit-fw"
            className={`cp-orbit-dd-trigger${filterOpen ? " is-open" : ""}`}
            aria-haspopup="listbox"
            aria-expanded={filterOpen}
            onClick={() => setFilterOpen((v) => !v)}
          >
            <span>{filterLabel}</span>
            <span className="cp-orbit-dd-chev" aria-hidden>
              ▾
            </span>
          </button>
          {filterOpen ? (
            <ul className="cp-orbit-dd-menu" role="listbox" aria-labelledby="cp-orbit-fw">
              {ORBIT_FILTERS.map((f) => {
                const label = f === "all" ? t("orbitFilterAll") : f;
                const on = filter === f;
                return (
                  <li key={f} role="option" aria-selected={on}>
                    <button
                      type="button"
                      className={`cp-orbit-dd-item${on ? " is-active" : ""}`}
                      onClick={() => {
                        setFilter(f);
                        setFilterOpen(false);
                      }}
                    >
                      {label}
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
      </div>
      {filtered.length === 0 ? (
        <div className="cp-fleet-loading" style={{ minHeight: 280 }}>
          <p className="cp-fleet-loading-title">{t("orbitEmpty")}</p>
          <button type="button" className="hud-btn" onClick={() => setFilter("all")}>
            {t("orbitFilterAll")}
          </button>
        </div>
      ) : (
        <div className="cp-orbit-wrap">
          <div className="cp-orbit-ring" aria-hidden />
          <div className="cp-orbit-core" aria-hidden>
            <div className="cp-orbit-binary">
              <span className="cp-orbit-star primary" />
              <span className="cp-orbit-star companion" />
            </div>
          </div>
          {nodes.map(({ ag, left, top }) => {
            const on = selected?.id === ag.id;
            const fw = agentFrameworkLabel(ag);
            const label = ag.name || ag.id;
            return (
              <button
                key={ag.id}
                type="button"
                className={`cp-orbit-node${on ? " is-on" : ""}`}
                style={{ left: `${left}%`, top: `${top}%` }}
                aria-label={`${label}${fw ? ` · ${fw}` : ""}`}
                aria-pressed={on}
                onClick={() => {
                  setLaunchErr("");
                  setLaunchMsg("");
                  setSelected(ag);
                }}
              >
                <img
                  src={portraitPath(ag.id)}
                  alt=""
                  className="cp-orbit-avatar"
                  draggable={false}
                  onError={(e) => {
                    const el = e.currentTarget;
                    el.style.display = "none";
                    const sib = el.nextElementSibling;
                    if (sib && sib.classList.contains("cp-orbit-avatar-fallback")) return;
                    const ph = document.createElement("span");
                    ph.className = "cp-orbit-avatar-fallback";
                    ph.textContent = (label || ag.id).slice(0, 1);
                    el.parentElement?.insertBefore(ph, el.nextSibling);
                  }}
                />
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      )}
      <HudL3Modal
        variant="portrait"
        title={selected?.name || selected?.id || ""}
        open={!!selected}
        onClose={() => setSelected(null)}
      >
        {selected && (
          <PortraitHud
            agent={selected}
            launchingMode={launchingMode}
            launchMsg={launchMsg}
            launchErr={launchErr}
            onLaunch={(id, mode) => void launch(id, mode)}
          />
        )}
      </HudL3Modal>
    </div>
  );
}
