import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Shell } from "./components/Shell";
import { CockpitPrototype } from "./components/CockpitPrototype";
import { CommandWindow, CommandWindowButton } from "./components/commandwindow/CommandWindow";
import { AssistantWindow } from "./components/assistant/AssistantWindow";
import { ConsoleApp } from "./pages/console/ConsoleApp";
import { HomePage } from "./pages/HomePage";
import { ClinicPage } from "./pages/ClinicPage";
import { ManagerDeskPage } from "./pages/ManagerDeskPage";
import { getUiMode, setUiMode } from "./lib/ui-mode";
import { t } from "./lib/i18n";
import { AuthTokenBanner } from "./components/AuthTokenBanner";
import { WriteFailToast } from "./components/WriteFailToast";
import { DemoModeBanner } from "./components/DemoModeBanner";

/**
 * 逃生舱侧栏：舰桥 + 配置/诊所/协调台（不再挂「首页」入口；/legacy 仍可直达排障页）。
 */
const NAV = [
  { to: "/", labelKey: "cockpitUi" as const },
  { to: "/clinic", label: "诊所" },
  { to: "/manager", label: "协调台" },
] as const;

/** 旧直链 → 舰桥主入口 */
function ToCockpit() {
  useEffect(() => {
    setUiMode("cockpit");
  }, []);
  return <Navigate to="/" replace />;
}

function UiModeSwitch({ mode }: { mode: "cockpit" | "legacy" }) {
  const nav = useNavigate();
  return (
    <div className="mb-3 space-y-2 px-3">
      <p className="rounded border border-amber-signal/40 bg-amber-signal/10 px-2 py-1.5 text-[11px] leading-snug text-amber-signal">
        {t("legacyEscapeHint")}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={`rounded px-2 py-1 text-xs ${mode === "cockpit" ? "bg-rail text-frost" : "text-mute"}`}
          onClick={() => {
            setUiMode("cockpit");
            nav("/");
          }}
        >
          {t("cockpitUi")}
        </button>
        <button
          type="button"
          className={`rounded px-2 py-1 text-xs ${mode === "legacy" ? "bg-rail text-frost" : "text-mute"}`}
          onClick={() => {
            setUiMode("legacy");
            nav("/legacy");
          }}
        >
          {t("legacyUi")}
        </button>
      </div>
    </div>
  );
}

function LegacyApp() {
  return (
    <Shell
      nav={
        <>
          <UiModeSwitch mode="legacy" />
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={"end" in item ? Boolean(item.end) : false}
              className={({ isActive }) =>
                [
                  "block rounded px-3 py-2 font-body text-[13px] transition",
                  isActive ? "nav-active" : "text-mute hover:bg-rail/40 hover:text-frost",
                ].join(" ")
              }
            >
              {"labelKey" in item ? t(item.labelKey) : item.label}
            </NavLink>
          ))}
          <p className="mt-4 px-3 text-[10px] leading-relaxed text-mute">{t("legacyMoreRoutes")}</p>
        </>
      }
    >
      <Routes>
        <Route path="/legacy" element={<HomePage />} />
        <Route path="/showcase" element={<Navigate to="/" replace />} />
        <Route path="/config" element={<ToCockpit />} />
        <Route path="/clinic" element={<ClinicPage />} />
        <Route path="/manager" element={<ManagerDeskPage />} />
        {/* 旧直链收口：回舰桥 */}
        <Route path="/tasks" element={<ToCockpit />} />
        <Route path="/inbox" element={<ToCockpit />} />
        <Route path="/discover" element={<ToCockpit />} />
        <Route path="/audit" element={<ToCockpit />} />
        <Route path="/human-queue" element={<ToCockpit />} />
        <Route path="/reviews" element={<ToCockpit />} />
        <Route path="/integrations" element={<ToCockpit />} />
        <Route path="*" element={<ToCockpit />} />
      </Routes>
    </Shell>
  );
}

function CockpitEntry() {
  const mode = getUiMode();
  if (mode === "legacy") {
    return <Navigate to="/legacy" replace />;
  }
  return (
    <>
      <div className="fixed bottom-3 right-3 z-[80]">
        <button
          type="button"
          className="rounded border border-rail bg-hull/90 px-3 py-1.5 font-mono text-xs text-mute shadow hover:text-frost"
          title={t("legacyEscapeHint")}
          onClick={() => {
            setUiMode("legacy");
            window.location.href = "/legacy";
          }}
        >
          {t("legacyUi")} ⇄
        </button>
      </div>
      <CockpitPrototype />
    </>
  );
}

export default function App() {
  const [cmdOpen, setCmdOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  return (
    <>
      <AuthTokenBanner />
      <WriteFailToast />
      <DemoModeBanner />
      {/* P1 发令交互窗口（D1 双向指挥席位）— 全局抽屉，双舱皆可唤起 */}
      <CommandWindowButton state={{ open: cmdOpen, setOpen: setCmdOpen }} />
      <CommandWindow state={{ open: cmdOpen, setOpen: setCmdOpen }} />
      {/* P2 AI 助手（D10/D11）— 全局浮窗，双舱皆可唤起 */}
      <button
        type="button"
        className="fixed bottom-16 right-24 z-[85] rounded-full border border-rail bg-hull/90 px-4 py-2 font-mono text-xs text-frost shadow hover:bg-rail/60"
        title="AI 助手 · 指标问答与手册检索"
        onClick={() => setAssistantOpen(!assistantOpen)}
      >
        🤖 助手
      </button>
      <AssistantWindow open={assistantOpen} onClose={() => setAssistantOpen(false)} />
      <Routes>
        <Route path="/" element={<CockpitEntry />} />
        <Route path="/cockpit" element={<CockpitEntry />} />
        {/* P3 管理中心（新主入口）；/legacy 保留 redirect 兼容历史直链 */}
        <Route path="/console/*" element={<ConsoleApp />} />
        <Route path="/legacy" element={<Navigate to="/console" replace />} />
        <Route path="/*" element={<LegacyApp />} />
      </Routes>
    </>
  );
}
