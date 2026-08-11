import { useEffect, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { ErrorAlert } from "./ErrorAlert";
import type { AgentProfile, AgentRow } from "../lib/agents";

type Props = {
  agent: AgentRow;
  busy?: boolean;
  launchingMode?: "browser" | "cli" | "client" | null;
  launchMsg?: string;
  launchErr?: string;
  onLaunch: (id: string, mode: "browser" | "cli" | "client") => void;
};

type AccessResp = {
  agent?: string;
  online?: boolean;
  browser?: {
    configured?: boolean;
    ok?: boolean;
    url?: string;
    status?: number | null;
    error?: string | null;
  };
  cli?: {
    configured?: boolean;
    ok?: boolean;
    via_api?: boolean;
    script?: string;
    error?: string | null;
  };
  launch?: Partial<AgentRow>;
  paths?: {
    identity?: string | null;
    identity_ok?: boolean;
    soul?: string | null;
    soul_ok?: boolean;
    cards_ok?: boolean;
  };
};

function AccessPill({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean | null;
  detail: string;
}) {
  const tone =
    ok === true
      ? "text-mint border-mint/30 bg-mint/10"
      : ok === false
        ? "text-flare border-flare/30 bg-flare/10"
        : "text-mute border-rail bg-hull/40";
  const mark = ok === true ? "可达" : ok === false ? "不可达" : "检测中";
  return (
    <div className={`rounded border px-2 py-1 text-[11px] ${tone}`}>
      <span className="font-mono uppercase tracking-wide">{label}</span>
      <span className="mx-1 opacity-60">·</span>
      <span>{mark}</span>
      {detail ? (
        <p className="mt-0.5 truncate font-mono text-[10px] opacity-80">{detail}</p>
      ) : null}
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

function portraitPath(id: string) {
  return `/avatars/${encodeURIComponent(id)}_portrait.png`;
}
function animatedPath(id: string) {
  return `/avatars/${encodeURIComponent(id)}_animated.webp`;
}

export function PortraitHud({
  agent,
  busy,
  launchingMode,
  launchMsg,
  launchErr,
  onLaunch,
}: Props) {
  const [profile, setProfile] = useState<AgentProfile | null>(null);
  const [access, setAccess] = useState<AccessResp | null>(null);
  const [err, setErr] = useState("");
  const [full, setFull] = useState(false);
  const [meta, setMeta] = useState<Partial<AgentRow>>(agent);
  const launching = !!launchingMode || !!busy;

  useEffect(() => {
    let cancelled = false;
    setErr("");
    setFull(false);
    setProfile(null);
    setAccess(null);
    setMeta(agent);
    void Promise.all([
      api<AgentProfile>(`/api/agent-profile/${encodeURIComponent(agent.id)}`),
      api<AccessResp>(`/api/ping/${encodeURIComponent(agent.id)}`),
    ]).then(([p, a]) => {
      if (cancelled) return;
      if (p.ok) setProfile(p.data);
      else setErr(p.error);
      if (a.ok) {
        setAccess(a.data);
        if (a.data.launch) setMeta((m) => ({ ...m, ...a.data.launch }));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [agent.id]);

  const card = (profile?.card || {}) as NonNullable<AgentProfile["card"]>;
  const cfg = (profile?.config || {}) as Record<string, unknown>;
  const name = String(card.name || cfg.name || meta.name || agent.name || agent.id);
  const role = String(card.role || cfg.role || meta.role || agent.role || "—");
  const type = String(cfg.type || meta.type || agent.framework || "?");
  const models = (Array.isArray(cfg.models) ? (cfg.models as string[]) : meta.models) || [];
  const modes = meta.launch_modes || agent.launch_modes || [];
  const showBrowser = meta.has_browser === true || modes.includes("browser");
  const showCli = modes.includes("cli") || true;
  const showDesktop = meta.has_desktop === true || modes.includes("desktop");
  const portrait = profile?.avatar_url
    ? `/${profile.avatar_url.replace(/^\//, "")}`
    : portraitPath(agent.id);
  const animated = profile?.avatar_animated
    ? `/${profile.avatar_animated.replace(/^\//, "")}`
    : animatedPath(agent.id);
  const browserOk = access?.browser ? !!access.browser.ok : null;
  const cliOk = access?.cli ? !!access.cli.ok : null;
  const hasFull = !!(
    card.strengths ||
    card.weaknesses ||
    card.abilities ||
    card.catchphrases?.length ||
    card.social ||
    (profile?.skills || []).length > 0
  );

  return (
    <div className="cp-portrait space-y-3">
      <ErrorAlert message={err} />

      <div className="grid gap-3 md:grid-cols-[160px_1fr]">
        <div className="cp-portrait-frame !w-full">
          <img
            src={animated}
            alt=""
            className="cp-portrait-anim"
            onError={(e) => {
              const el = e.target as HTMLImageElement;
              if (el.src.includes("_animated")) el.src = portrait;
              else el.style.display = "none";
            }}
          />
        </div>

        <div className="space-y-2 text-sm">
          <div>
            <p className="font-display text-lg text-frost">
              {name}{" "}
              <span className="text-sm font-normal text-mute">{type}</span>
            </p>
            <p className="font-mono text-[11px] text-mute">{agent.id}</p>
            <p className="mt-1 text-sm text-mute">{role}</p>
          </div>

          <div className="flex flex-wrap gap-2 font-mono text-[11px] text-mute">
            <span>
              消息 <strong className="text-frost">{profile?.messages ?? 0}</strong>
            </span>
            <span>
              未读 <strong className="text-cyan-signal">{profile?.unread ?? 0}</strong>
            </span>
            <span>
              技能 <strong className="text-frost">{(profile?.skills || []).length}</strong>
            </span>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <AccessPill
              label="浏览器"
              ok={showBrowser ? browserOk : false}
              detail={
                showBrowser
                  ? access?.browser?.url || meta.launch_url || "未配置URL"
                  : "未挂载浏览器入口"
              }
            />
            <AccessPill
              label="终端"
              ok={cliOk}
              detail={
                access?.cli?.via_api
                  ? "API启动"
                  : access?.cli?.script
                    ? "launch脚本可用"
                    : "检测launch脚本"
              }
            />
          </div>
        </div>
      </div>

      {/* 基本信息 */}
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
        {card.archetype || agent.archetype ? (
          <InfoCell label="Archetype">
            {String(card.archetype || agent.archetype)}
          </InfoCell>
        ) : null}
      </div>

      {(card.personality || card.ziyan_bond) && (
        <InfoCell label="性格 / 关系">
          <span className="whitespace-pre-wrap text-mute">
            {String(card.personality || card.ziyan_bond).slice(0, 400)}
          </span>
        </InfoCell>
      )}

      {card.motto ? (
        <InfoCell label="座右铭">
          <span className="italic text-cyan-signal">“{card.motto}”</span>
        </InfoCell>
      ) : null}

      {Array.isArray(card.traits) && card.traits.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {card.traits.slice(0, 8).map((t) => (
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
        <p className="font-mono text-[11px] text-mute">
          模型：{models.join(", ")}
        </p>
      )}

      {/* 完整档案 — 结构化字段 */}
      {full && (
        <div className="space-y-3 rounded border border-rail bg-abyss/30 p-3">
          {card.strengths && (
            <InfoCell label="优势">{card.strengths}</InfoCell>
          )}
          {card.weaknesses && (
            <InfoCell label="劣势">{card.weaknesses}</InfoCell>
          )}
          {card.abilities && (
            <InfoCell label="能力">{card.abilities}</InfoCell>
          )}
          {card.social && (
            <InfoCell label="社交">{card.social}</InfoCell>
          )}
          {Array.isArray(card.catchphrases) && card.catchphrases.length > 0 && (
            <div>
              <p className="hud-label !normal-case !tracking-normal">口头禅</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {card.catchphrases.map((cp, i) => (
                  <span
                    key={i}
                    className="rounded border border-amber/30 bg-amber/5 px-2 py-0.5 text-xs text-amber"
                  >
                    {cp}
                  </span>
                ))}
              </div>
            </div>
          )}
          {(profile?.skills || []).length > 0 && (
            <div>
              <p className="hud-label !normal-case !tracking-normal">
                技能清单 ({profile?.skills?.length || 0})
              </p>
              <div className="mt-1 flex flex-wrap gap-1">
                {(profile?.skills || []).map((sk) => (
                  <span
                    key={sk}
                    className="rounded border border-mint/20 bg-mint/5 px-2 py-0.5 font-mono text-[10px] text-mint"
                  >
                    {sk}
                  </span>
                ))}
              </div>
            </div>
          )}
          {profile?.soul && (
            <details>
              <summary className="cursor-pointer text-xs text-mute hover:text-frost">
                SOUL 人设
              </summary>
              <pre className="mt-2 max-h-48 overflow-auto rounded border border-rail bg-abyss/60 p-2 font-mono text-[10px] leading-relaxed text-mute whitespace-pre-wrap">
                {profile.soul.slice(0, 3000)}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* 操作栏 */}
      <div className="flex flex-wrap gap-2 border-t border-rail pt-3">
        {showBrowser && (
          <button
            type="button"
            className="hud-btn"
            disabled={launching}
            title={meta.launch_url || ""}
            onClick={() => onLaunch(agent.id, "browser")}
          >
            {launchingMode === "browser" ? "…" : "浏览器"}
          </button>
        )}
        {showCli && (
          <button
            type="button"
            className="hud-btn"
            disabled={launching || cliOk === false}
            onClick={() => onLaunch(agent.id, "cli")}
          >
            {launchingMode === "cli" ? "…" : "终端"}
          </button>
        )}
        {showDesktop && (
          <button
            type="button"
            className="hud-btn-amber"
            disabled={launching}
            onClick={() => onLaunch(agent.id, "client")}
          >
            {launchingMode === "client" ? "…" : "Client"}
          </button>
        )}
        {hasFull && (
          <button
            type="button"
            className="hud-btn !px-2"
            onClick={() => setFull((v) => !v)}
          >
            {full ? "收起档案" : "完整档案"}
          </button>
        )}
      </div>

      {launchMsg && <p className="text-xs text-mint">{launchMsg}</p>}
      {launchErr && <p className="text-xs text-flare">{launchErr}</p>}
    </div>
  );
}
