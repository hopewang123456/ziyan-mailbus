import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { ErrorAlert } from "./ErrorAlert";

export type AgentRow = {
  id: string;
  name?: string;
  role?: string;
  type?: string;
  framework?: string;
  archetype?: string;
  models?: string[];
  launch_modes?: string[];
  has_browser?: boolean;
  has_desktop?: boolean;
  launch_url?: string;
  enabled?: boolean;
  active_tasks?: number;
  queued_steps?: number;
  inbox_pending?: number;
  [k: string]: unknown;
};

type AgentsResp = { agents?: Record<string, Omit<AgentRow, "id">> };
type WorkloadResp = {
  agents?: Record<string, { active_tasks?: number; queued_steps?: number; inbox_pending?: number }>;
};

export type AgentProfile = {
  config?: Record<string, unknown>;
  card?: {
    name?: string;
    role?: string;
    age?: string;
    zodiac?: string;
    mbti?: string;
    gender?: string;
    motto?: string;
    traits?: string[];
    personality?: string;
    bond?: string;
    ziyan_bond?: string;
    animated?: string;
  };
  identity?: string;
  avatar_url?: string;
  avatar_animated?: string;
};

function avatarUrl(id: string, kind: "plain" | "portrait" | "animated" = "plain"): string {
  if (kind === "portrait") return `/avatars/${encodeURIComponent(id)}_portrait.svg`;
  if (kind === "animated") return `/avatars/${encodeURIComponent(id)}_animated.svg`;
  return `/avatars/${encodeURIComponent(id)}.svg`;
}

export function useFleetAgents() {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    setErr("");
    // Don't let workload/launch hang or fail block the roster (orbit needs agents first).
    const [a, w, launch] = await Promise.all([
      api<AgentsResp>("/api/agents"),
      api<WorkloadResp>("/api/workload"),
      api<{ agents?: Record<string, Partial<AgentRow>> }>("/api/launch"),
    ]);
    if (!a.ok) {
      setErr(a.error);
      setAgents([]);
      return;
    }
    const raw = a.data?.agents;
    const dict: Record<string, Partial<AgentRow>> = Array.isArray(raw)
      ? Object.fromEntries(
          (raw as Array<Partial<AgentRow> & { id?: string }>).map((row, i) => [
            String(row.id || `agent-${i}`),
            row,
          ]),
        )
      : ((raw || {}) as Record<string, Partial<AgentRow>>);
    const work = w.ok ? w.data.agents || {} : {};
    const launchMeta = launch.ok ? launch.data.agents || {} : {};
    const rows: AgentRow[] = Object.entries(dict).map(([id, cfg]) => {
      const lm = launchMeta[id] || {};
      return {
        id,
        ...cfg,
        ...lm,
        launch_modes: (lm.launch_modes as string[]) || cfg.launch_modes || ["cli"],
        has_browser: lm.has_browser ?? cfg.has_browser,
        has_desktop: lm.has_desktop ?? cfg.has_desktop,
        launch_url: (lm.launch_url as string) || cfg.launch_url,
        active_tasks: work[id]?.active_tasks ?? 0,
        queued_steps: work[id]?.queued_steps ?? 0,
        inbox_pending: work[id]?.inbox_pending ?? 0,
      };
    });
    rows.sort((x, y) => x.id.localeCompare(y.id));
    setAgents(rows);
    if (!rows.length) setErr("agents 列表为空");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function launch(id: string, mode: "browser" | "desktop" | "cli" = "browser") {
    setBusy(true);
    setMsg("");
    setErr("");
    const r = await api<{ message?: string; url?: string }>("/api/launch", {
      method: "POST",
      body: JSON.stringify({ agent: id, mode }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(r.data.message || `已启动 ${id}（${mode}）`);
      if (r.data.url) window.open(r.data.url, "_blank", "noopener,noreferrer");
    } else setErr(r.error);
  }

  async function setEnabled(id: string, enabled: boolean) {
    setBusy(true);
    const r = await api(`/api/agents/${encodeURIComponent(id)}/enable`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(`${id} → ${enabled ? "启用" : "停用"}`);
      void load();
    } else setErr(r.error);
  }

  return { agents, err, msg, busy, load, launch, setEnabled, setMsg, setErr };
}

/** 角色详情面板 — 对齐旧 HUD showAgent（profile + inbox） */
export function AgentDetailPanel({
  agent,
  busy,
  onLaunch,
  onClose,
}: {
  agent: AgentRow | null;
  busy?: boolean;
  onLaunch: (id: string, mode: "browser" | "desktop" | "cli") => void;
  onClose?: () => void;
}) {
  const [profile, setProfile] = useState<AgentProfile | null>(null);
  const [inbox, setInbox] = useState<{ total?: number; messages?: unknown[] } | null>(null);
  const [err, setErr] = useState("");
  const [full, setFull] = useState(false);

  useEffect(() => {
    if (!agent) {
      setProfile(null);
      setInbox(null);
      return;
    }
    let cancelled = false;
    setErr("");
    setFull(false);
    void Promise.all([
      api<AgentProfile>(`/api/agent-profile/${encodeURIComponent(agent.id)}`),
      api<{ total_messages?: number; messages?: unknown[] }>(
        `/api/inbox/${encodeURIComponent(agent.id)}`,
      ),
    ]).then(([p, i]) => {
      if (cancelled) return;
      if (p.ok) setProfile(p.data);
      else setErr(p.error);
      if (i.ok) {
        setInbox({
          total: i.data.total_messages,
          messages: Array.isArray(i.data.messages) ? i.data.messages : [],
        });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [agent?.id]);

  if (!agent) {
    return (
      <div className="soft-panel flex min-h-48 items-center justify-center p-6 text-sm text-mute">
        点击左侧卡片查看角色档案
      </div>
    );
  }

  const card = profile?.card || {};
  const cfg = profile?.config || {};
  const name = String(card.name || cfg.name || agent.name || agent.id);
  const role = String(card.role || cfg.role || agent.role || "—");
  const type = String(cfg.type || agent.type || agent.framework || "?");
  const models = (Array.isArray(cfg.models) ? cfg.models : agent.models) || [];
  const msgs = inbox?.messages || [];
  const privateMsgs = msgs.filter((m) => {
    const t = (m as { type?: string }).type;
    return t !== "system";
  });
  const unread = privateMsgs.filter((m) => !(m as { read?: boolean }).read);
  const modes = agent.launch_modes || [];
  const showBrowser = agent.has_browser !== false && (modes.includes("browser") || modes.length === 0);
  const showCli = modes.includes("cli") || true;
  const showDesktop = !!agent.has_desktop || modes.includes("desktop");
  const portrait = avatarUrl(agent.id, "portrait");
  const animated = avatarUrl(agent.id, "animated");

  return (
    <div className="soft-panel space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="hud-label">角色档案</p>
          <h3 className="mt-1 font-display text-xl font-semibold text-frost">
            {name}{" "}
            <span className="text-sm font-normal text-mute">{type}</span>
          </h3>
          <p className="mt-0.5 font-mono text-[11px] text-mute">{agent.id}</p>
        </div>
        {onClose && (
          <button type="button" className="hud-btn !px-2 !py-1" onClick={onClose}>
            关闭
          </button>
        )}
      </div>

      <ErrorAlert message={err} />

      <div className="grid gap-4 md:grid-cols-[200px_1fr]">
        <div className="overflow-hidden rounded border border-rail bg-abyss/60">
          <img
            src={animated}
            alt=""
            className="mx-auto max-h-56 w-full object-contain"
            onError={(e) => {
              const el = e.target as HTMLImageElement;
              if (el.src.includes("_animated")) el.src = portrait;
              else if (el.src.includes("_portrait")) el.src = avatarUrl(agent.id);
              else el.style.display = "none";
            }}
          />
        </div>

        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-3 font-mono text-[11px] text-mute">
            <span>
              消息 <strong className="text-frost">{inbox?.total ?? msgs.length}</strong>
            </span>
            <span>
              私信 <strong className="text-cyan-signal">{privateMsgs.length}</strong>
            </span>
            <span>
              未读 <strong className="text-cyan-signal">{unread.length}</strong>
            </span>
            <span>
              任务 <strong className="text-frost">{agent.active_tasks ?? 0}</strong>
            </span>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            {card.age || card.zodiac ? (
              <InfoCell label="年龄 · 星座">
                {[card.age, card.zodiac].filter(Boolean).join(" · ")}
              </InfoCell>
            ) : null}
            {card.gender ? <InfoCell label="性别">{card.gender}</InfoCell> : null}
            {card.mbti ? (
              <InfoCell label="MBTI">
                <span className="text-cyan-signal">{card.mbti}</span>
              </InfoCell>
            ) : null}
            {agent.archetype ? <InfoCell label="Archetype">{String(agent.archetype)}</InfoCell> : null}
          </div>

          <InfoCell label="角色">{role}</InfoCell>

          {(card.personality || card.bond || card.ziyan_bond) && (
            <InfoCell label="工作 / 性格">
              <span className="whitespace-pre-wrap text-mute">
                {String(card.personality || card.bond || card.ziyan_bond).slice(0, 400)}
              </span>
            </InfoCell>
          )}

          {card.motto && (
            <InfoCell label="座右铭">
              <span className="italic text-cyan-signal">“{card.motto}”</span>
            </InfoCell>
          )}

          {Array.isArray(card.traits) && card.traits.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {card.traits.slice(0, 6).map((t) => (
                <span
                  key={t}
                  className="rounded border border-cyan-signal/15 bg-cyan-signal/5 px-2 py-0.5 text-xs text-cyan-signal"
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          {models.length > 0 && (
            <p className="font-mono text-[11px] text-mute">模型：{models.join(", ")}</p>
          )}

          {agent.launch_url ? (
            <p className="truncate font-mono text-[10px] text-mute">URL {String(agent.launch_url)}</p>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-t border-rail pt-3">
        {showBrowser && (
          <button
            type="button"
            className="hud-btn"
            disabled={busy}
            onClick={() => onLaunch(agent.id, "browser")}
          >
            浏览器
          </button>
        )}
        {showCli && (
          <button
            type="button"
            className="hud-btn"
            disabled={busy}
            onClick={() => onLaunch(agent.id, "cli")}
          >
            CLI
          </button>
        )}
        {showDesktop && (
          <button
            type="button"
            className="hud-btn-amber"
            disabled={busy}
            onClick={() => onLaunch(agent.id, "desktop")}
          >
            Client
          </button>
        )}
        <button type="button" className="hud-btn !px-2" onClick={() => setFull((v) => !v)}>
          {full ? "收起档案" : "完整档案"}
        </button>
      </div>

      {full && profile?.identity && (
        <pre className="max-h-64 overflow-auto rounded border border-rail bg-abyss/50 p-3 font-mono text-[11px] leading-relaxed text-mute whitespace-pre-wrap">
          {profile.identity}
        </pre>
      )}
    </div>
  );
}

function InfoCell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded border border-rail/80 bg-abyss/40 px-3 py-2">
      <p className="hud-label !normal-case !tracking-normal">{label}</p>
      <div className="mt-1 text-frost">{children}</div>
    </div>
  );
}

type FleetProps = {
  selectedId?: string;
  onSelect?: (id: string) => void;
  /** 是否内嵌右侧详情（首页用） */
  withDetail?: boolean;
};

/** AI Agent 舰队 — 浏览器 / CLI / Client + 角色详情 */
export function FleetGrid({ selectedId, onSelect, withDetail }: FleetProps) {
  const { agents, err, msg, busy, load, launch } = useFleetAgents();
  const [localSel, setLocalSel] = useState(selectedId || "");
  const selId = selectedId ?? localSel;
  const selected = agents.find((a) => a.id === selId) || null;

  function pick(id: string) {
    setLocalSel(id);
    onSelect?.(id);
  }

  return (
    <div className={withDetail ? "grid gap-4 lg:grid-cols-5" : "space-y-4"}>
      <div className={`space-y-4 ${withDetail ? "lg:col-span-3" : ""}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="hud-label">AI Agent 舰队</p>
            <p className="mt-1 text-sm text-mute">
              {agents.length} 名 · 浏览器 / CLI / Client
            </p>
          </div>
          <button type="button" className="hud-btn" disabled={busy} onClick={() => void load()}>
            刷新
          </button>
        </div>
        <ErrorAlert message={err} />
        {msg && <p className="text-xs text-mint">{msg}</p>}

        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {agents.length === 0 && !err && (
            <li className="text-sm text-mute">暂无 agent</li>
          )}
          {agents.map((ag) => {
            const active = selId === ag.id;
            const modes = ag.launch_modes || [];
            const canBrowser =
              ag.has_browser !== false && (modes.includes("browser") || !modes.length);
            const canDesktop = !!ag.has_desktop || modes.includes("desktop");
            return (
              <li key={ag.id}>
                <div
                  className={`soft-inset transition hover:border-white/15 ${
                    active ? "border-cyan-signal/50 bg-cyan-signal/5" : ""
                  }`}
                >
                  <button type="button" className="w-full text-left" onClick={() => pick(ag.id)}>
                    <div className="flex items-start gap-3">
                      <img
                        src={avatarUrl(ag.id)}
                        alt=""
                        width={40}
                        height={40}
                        className="h-10 w-10 shrink-0 rounded"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.visibility = "hidden";
                        }}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-display text-sm font-semibold text-frost">
                            {ag.name || ag.id}
                          </span>
                          <span className="rounded bg-cyan-signal/10 px-1.5 py-0.5 font-mono text-[10px] text-cyan-signal">
                            {ag.type || ag.framework || "?"}
                          </span>
                        </div>
                        <p className="mt-0.5 line-clamp-2 text-xs text-mute">{ag.role || ag.id}</p>
                        <p className="mt-2 flex flex-wrap gap-3 font-mono text-[10px] text-mute">
                          <span>任务 {ag.active_tasks ?? 0}</span>
                          <span>队列 {ag.queued_steps ?? 0}</span>
                          <span>信箱 {ag.inbox_pending ?? 0}</span>
                        </p>
                      </div>
                    </div>
                  </button>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {canBrowser && (
                      <button
                        type="button"
                        className="hud-btn !px-2 !py-1"
                        disabled={busy}
                        onClick={() => void launch(ag.id, "browser")}
                      >
                        浏览器
                      </button>
                    )}
                    <button
                      type="button"
                      className="hud-btn !px-2 !py-1"
                      disabled={busy}
                      onClick={() => void launch(ag.id, "cli")}
                    >
                      CLI
                    </button>
                    {canDesktop && (
                      <button
                        type="button"
                        className="hud-btn-amber !px-2 !py-1"
                        disabled={busy}
                        onClick={() => void launch(ag.id, "desktop")}
                      >
                        Client
                      </button>
                    )}
                    <button
                      type="button"
                      className="hud-btn !px-2 !py-1 text-mute"
                      disabled={busy}
                      onClick={() => pick(ag.id)}
                    >
                      详情
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {withDetail && (
        <div className="lg:col-span-2">
          <AgentDetailPanel
            agent={selected}
            busy={busy}
            onLaunch={(id, mode) => void launch(id, mode)}
          />
        </div>
      )}
    </div>
  );
}
