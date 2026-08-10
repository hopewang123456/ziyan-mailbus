import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { TwinStarsLogo } from "./TwinStarsLogo";
import { SpaceFlybyHost } from "./SpaceFlybyHost";
import { CockpitHudBody, type HudPanelId } from "./CockpitHudBody";
import { getLang, t, type I18nKey } from "../lib/i18n";
import { playClickSfx, setCockpitMuted, unlockCockpitAudio } from "../lib/cockpit-audio";
import "./cockpit-prototype.css";

type TopZone = "left" | "center" | "right" | null;
type PanelId =
  | "home"
  | "tasks"
  | "agents"
  | "llm"
  | "integrations"
  | "bus"
  | "other"
  | "clinic"
  | "mute";

type HotspotId =
  | "clinic"
  | "other"
  | "tasks"
  | "setA"
  | "setB"
  | "setC";

type Hotspot = {
  id: HotspotId;
  labelKey: I18nKey;
  left: number;
  top: number;
  width: number;
  height: number;
  sfx: "soft" | "clack" | "chirp" | "thud";
  panel: Exclude<PanelId, "mute" | "home" | "agents">;
};

const STORAGE_KEY = "mailbus.cockpit.hotspots.v3";

/** 三旋钮分功能：模型 / 集成 / 总线（2026-08-01 控制台图校准） */
const DEFAULT_HOTSPOTS: Hotspot[] = [
  { id: "clinic", labelKey: "clinic", left: 6.19, top: 57.1, width: 4.56, height: 7.25, sfx: "soft", panel: "clinic" },
  { id: "other", labelKey: "other", left: 16.89, top: 50.11, width: 24.82, height: 20.18, sfx: "soft", panel: "other" },
  { id: "tasks", labelKey: "tasks", left: 46.12, top: 21.3, width: 12, height: 42, sfx: "thud", panel: "tasks" },
  { id: "setA", labelKey: "llm", left: 65.19, top: 55.08, width: 4.68, height: 8.06, sfx: "soft", panel: "llm" },
  { id: "setB", labelKey: "integrations", left: 73.29, top: 54.92, width: 4.38, height: 8.06, sfx: "soft", panel: "integrations" },
  { id: "setC", labelKey: "bus", left: 81.39, top: 55.25, width: 4.38, height: 7.52, sfx: "soft", panel: "bus" },
];

const PANEL_KEYS: Record<
  Exclude<PanelId, "mute">,
  { titleKey: I18nKey; blurbZh: string; blurbEn: string }
> = {
  home: { titleKey: "home", blurbZh: "子言情境 · 健康指标", blurbEn: "Context · health" },
  tasks: { titleKey: "tasks", blurbZh: "任务 / 审计 / 人机", blurbEn: "Tasks / audit / human" },
  agents: { titleKey: "agents", blurbZh: "智能体员工 · 齐套后启用", blurbEn: "Crew · after avatars ready" },
  llm: { titleKey: "llm", blurbZh: "模型配置 | 智能体配置", blurbEn: "Models | Agents" },
  integrations: { titleKey: "integrations", blurbZh: "限界集成 · AgentMemory", blurbEn: "Integrations · AgentMemory" },
  bus: { titleKey: "bus", blurbZh: "通道 · 路径 · 权限 · A2A", blurbEn: "Channels · paths · permission · A2A" },
  other: { titleKey: "other", blurbZh: "卡片入口 · 三级弹层", blurbEn: "Cards · L3 modals" },
  clinic: { titleKey: "clinic", blurbZh: "诊断与健康", blurbEn: "Diagnostics & health" },
};

function loadHotspots(): Hotspot[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_HOTSPOTS;
    const parsed = JSON.parse(raw) as Array<Partial<Hotspot>>;
    if (!Array.isArray(parsed) || parsed.length !== DEFAULT_HOTSPOTS.length) {
      return DEFAULT_HOTSPOTS;
    }
    return DEFAULT_HOTSPOTS.map((d, i) => {
      const p = parsed[i];
      if (!p || p.id !== d.id) return d;
      return {
        ...d,
        left: typeof p.left === "number" ? p.left : d.left,
        top: typeof p.top === "number" ? p.top : d.top,
        width: typeof p.width === "number" ? p.width : d.width,
        height: typeof p.height === "number" ? p.height : d.height,
      };
    });
  } catch {
    return DEFAULT_HOTSPOTS;
  }
}

function playClick(kind: "soft" | "clack" | "chirp" | "thud") {
  playClickSfx(kind);
}

type DragState =
  | null
  | {
      id: HotspotId;
      mode: "move" | "resize";
      startX: number;
      startY: number;
      orig: Hotspot;
    };

export function CockpitPrototype() {
  const stageRef = useRef<HTMLDivElement>(null);
  const hudRef = useRef<HTMLDivElement>(null);
  /** 仅悬停下方时显示控制台；默认始终玻璃窗 */
  const [hoverConsole, setHoverConsole] = useState(false);
  const [topZone, setTopZone] = useState<TopZone>(null);
  const [panel, setPanel] = useState<Exclude<PanelId, "mute"> | null>(null);
  const [muted, setMuted] = useState(false);
  const [booting, setBooting] = useState(true);
  const [acting, setActing] = useState<HotspotId | PanelId | null>(null);
  const [charging, setCharging] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [hotspots, setHotspots] = useState<Hotspot[]>(() => loadHotspots());
  const [drag, setDrag] = useState<DragState>(null);
  const [lang, setLangTick] = useState(() => getLang());

  const showConsole = (hoverConsole || editMode) && !panel;

  useEffect(() => {
    const t = window.setTimeout(() => setBooting(false), 1000);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(() => {
    const onLang = () => setLangTick(getLang());
    window.addEventListener("mailbus:lang", onLang);
    return () => window.removeEventListener("mailbus:lang", onLang);
  }, []);

  useEffect(() => {
    setCockpitMuted(muted);
  }, [muted]);

  useEffect(() => {
    const onHotspotEdit = () => {
      setPanel(null);
      setEditMode(true);
      setHoverConsole(true);
    };
    window.addEventListener("mailbus:hotspot-edit", onHotspotEdit);
    return () => window.removeEventListener("mailbus:hotspot-edit", onHotspotEdit);
  }, []);

  useEffect(() => {
    if (!panel || editMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPanel(null);
    };
    window.addEventListener("keydown", onKey);
    const root = hudRef.current;
    const focusable = root?.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    focusable?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [panel, editMode]);

  const onStagePointerDown = useCallback(() => {
    unlockCockpitAudio();
  }, []);

  const onMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (editMode || drag || panel) return;
      const el = stageRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width;
      const y = (e.clientY - r.top) / r.height;

      if (y >= 0.55) {
        setHoverConsole((h) => (h ? h : true));
        setTopZone((z) => (z == null ? z : null));
        return;
      }

      setHoverConsole((h) => (h ? false : h));
      if (y <= 0.34) {
        const next: TopZone = x < 0.33 ? "left" : x > 0.66 ? "right" : "center";
        setTopZone((z) => (z === next ? z : next));
      } else {
        setTopZone((z) => (z == null ? z : null));
      }
    },
    [editMode, drag, panel],
  );

  const openFromHotspot = useCallback(
    (hs: Hotspot) => {
      if (editMode || charging) return;
      setActing(hs.id);
      playClick(hs.sfx);

      /* 任务杆：整图难做真下拉 → 充能动画后再开主屏 */
      if (hs.id === "tasks") {
        setCharging(true);
        window.setTimeout(() => {
          setCharging(false);
          setActing(null);
          setHoverConsole(false);
          setPanel(hs.panel);
        }, 720);
        return;
      }

      window.setTimeout(() => setActing(null), 650);
      window.setTimeout(() => {
        setHoverConsole(false);
        setPanel(hs.panel);
      }, 280);
    },
    [editMode, charging],
  );

  const openTop = useCallback(
    (id: PanelId, sfx: "soft" | "clack" | "chirp" | "thud") => {
      if (editMode) return;
      setActing(id);
      window.setTimeout(() => setActing(null), 700);
      playClick(sfx);
      if (id === "mute") {
        setMuted((m) => {
          const next = !m;
          setCockpitMuted(next);
          return next;
        });
        return;
      }
      setHoverConsole(false);
      setPanel(id);
    },
    [editMode],
  );

  const saveHotspots = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(hotspots));
  }, [hotspots]);

  const resetHotspots = useCallback(() => {
    setHotspots(DEFAULT_HOTSPOTS);
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem("mailbus.cockpit.hotspots.v1");
    localStorage.removeItem("mailbus.cockpit.hotspots.v2");
  }, []);

  const onHsPointerDown = useCallback(
    (e: ReactPointerEvent, id: HotspotId, mode: "move" | "resize") => {
      if (!editMode) return;
      e.preventDefault();
      e.stopPropagation();
      const hs = hotspots.find((h) => h.id === id);
      if (!hs) return;
      setDrag({
        id,
        mode,
        startX: e.clientX,
        startY: e.clientY,
        orig: { ...hs },
      });
    },
    [editMode, hotspots],
  );

  const onStagePointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      onMove(e);
      if (!drag || !stageRef.current) return;
      const r = stageRef.current.getBoundingClientRect();
      const dx = ((e.clientX - drag.startX) / r.width) * 100;
      const dy = ((e.clientY - drag.startY) / r.height) * 100;
      setHotspots((list) =>
        list.map((h) => {
          if (h.id !== drag.id) return h;
          if (drag.mode === "move") {
            return {
              ...h,
              left: Math.min(95, Math.max(0, drag.orig.left + dx)),
              top: Math.min(95, Math.max(0, drag.orig.top + dy)),
            };
          }
          return {
            ...h,
            width: Math.min(40, Math.max(3, drag.orig.width + dx)),
            height: Math.min(40, Math.max(3, drag.orig.height + dy)),
          };
        }),
      );
    },
    [drag, onMove],
  );

  const meta = panel
    ? {
        title: t(PANEL_KEYS[panel].titleKey, lang),
        blurb: lang === "en" ? PANEL_KEYS[panel].blurbEn : PANEL_KEYS[panel].blurbZh,
      }
    : null;
  const exportText = useMemo(() => JSON.stringify(hotspots, null, 2), [hotspots]);

  return (
    <div className={`cp-root ${booting ? "is-booting" : ""} ${editMode ? "is-edit" : ""}`}>
      {booting && (
        <div className="cp-boot" role="status">
          <TwinStarsLogo size={56} />
          <p>{t("booting", lang)}</p>
        </div>
      )}

      {editMode && (
        <div className="cp-toolbar">
          <button
            type="button"
            className="is-on"
            onClick={() => {
              setEditMode(false);
              setPanel(null);
              setHoverConsole(false);
            }}
          >
            {t("exitCalibrate", lang)}
          </button>
          <button type="button" onClick={saveHotspots}>
            {t("saveHotspots", lang)}
          </button>
          <button type="button" onClick={resetHotspots}>
            {t("resetHotspots", lang)}
          </button>
          <button
            type="button"
            onClick={() => void navigator.clipboard?.writeText(exportText)}
          >
            {t("copyJson", lang)}
          </button>
        </div>
      )}

      <div
        ref={stageRef}
        className={`cp-stage ${showConsole ? "scene-console" : "scene-glass"}`}
        onPointerDown={onStagePointerDown}
        onPointerMove={onStagePointerMove}
        onPointerUp={() => setDrag(null)}
        onPointerLeave={() => {
          setTopZone(null);
          setHoverConsole(false);
          setDrag(null);
        }}
      >
        {/* 窗外景色：Canvas 永不挂 filter/opacity，变暗只用遮罩，避免 WebGL 层重建 */}
        <div className="cp-layer cp-space-persist" aria-hidden>
          <SpaceFlybyHost />
        </div>
        <div className="cp-layer cp-glass-view">
          <div className={`cp-glass-veil ${showConsole ? "is-on" : ""}`} />
          <div className="cp-glass-frame" />
        </div>

        <img
          className={`cp-layer cp-console-view ${showConsole ? "is-show" : ""}`}
          src="/cockpit/console-complete-v1.png"
          alt="控制台"
          draggable={false}
        />

        <div className="cp-top-rail" aria-hidden />

        <button
          type="button"
          className={`cp-drop zone-left is-photo ${topZone === "left" || muted || editMode ? "is-show" : ""} ${muted ? "is-act" : ""}`}
          aria-label={t("mute", lang)}
          onClick={() => openTop("mute", "soft")}
        >
          <span className="cp-hang">
            <span className="cp-hang-hook" aria-hidden />
            <img
              className="cp-hang-img"
              src="/cockpit/props/top-headphones-alpha.png"
              alt=""
              draggable={false}
            />
          </span>
          <span className="cp-plate-tag">{t("mute", lang)}</span>
        </button>

        <button
          type="button"
          className={`cp-drop zone-center is-photo ${topZone === "center" || editMode ? "is-show" : ""}`}
          aria-label={t("home", lang)}
          onClick={() => openTop("home", "chirp")}
        >
          <span className="cp-hang">
            <span className="cp-hang-hook" aria-hidden />
            <img
              className="cp-hang-img"
              src="/cockpit/props/top-badge-alpha.png"
              alt=""
              draggable={false}
            />
          </span>
          <span className="cp-plate-tag">{t("home", lang)}</span>
        </button>

        <button
          type="button"
          className={`cp-drop zone-right is-photo ${topZone === "right" || panel === "agents" || editMode ? "is-show" : ""} ${panel === "agents" || acting === "agents" ? "is-act" : ""}`}
          aria-label={t("agents", lang)}
          onClick={() => openTop("agents", "clack")}
        >
          <span className="cp-hang">
            <span className="cp-hang-hook" aria-hidden />
            <img
              className="cp-hang-img"
              src="/cockpit/props/top-intercom-v2-alpha.png"
              alt=""
              draggable={false}
            />
          </span>
          <span className="cp-plate-tag">{t("agents", lang)}</span>
        </button>

        <div className={`cp-hotspots ${showConsole || editMode ? "is-show" : ""}`}>
          {hotspots.map((h) => (
            <button
              key={h.id}
              type="button"
              className={`cp-hs hs-${h.id} ${panel === h.panel ? "is-on" : ""} ${acting === h.id ? "is-act" : ""} ${h.id === "tasks" && charging ? "is-charging" : ""} ${editMode ? "is-edit" : ""}`}
              style={{
                left: `${h.left}%`,
                top: `${h.top}%`,
                width: `${h.width}%`,
                height: `${h.height}%`,
              }}
              aria-label={t(h.labelKey, lang)}
              onClick={() => openFromHotspot(h)}
              onPointerDown={(e) => onHsPointerDown(e, h.id, "move")}
            >
              <span className="cp-hs-fx" aria-hidden />
              {h.id === "tasks" && (
                <span className="cp-charge" aria-hidden>
                  <span className="cp-charge-fill" />
                  <span className="cp-charge-label">{t("charge", lang)}</span>
                </span>
              )}
              <span className="cp-plate-tag">{t(h.labelKey, lang)}</span>
              {editMode && (
                <span
                  className="cp-hs-resize"
                  onPointerDown={(e) => onHsPointerDown(e, h.id, "resize")}
                />
              )}
            </button>
          ))}
        </div>

        {meta && panel && !editMode && (
          <div
            ref={hudRef}
            className="cp-hud"
            role="dialog"
            aria-modal="true"
            aria-label={meta.title}
          >
            <div className="cp-hud-frost" />
            <header className="cp-hud-head">
              <div>
                <h2>{meta.title}</h2>
                <p className="cp-hud-blurb">{meta.blurb}</p>
              </div>
              <button
                type="button"
                className="cp-icon-x"
                aria-label={t("close", lang)}
                onClick={() => setPanel(null)}
              >
                ×
              </button>
            </header>
            <div className="cp-hud-body">
              <CockpitHudBody panel={panel as HudPanelId} />
            </div>
          </div>
        )}

        {editMode && <p className="cp-edit-tip">{t("editTip", lang)}</p>}
      </div>
    </div>
  );
}
