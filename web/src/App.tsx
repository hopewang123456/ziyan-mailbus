import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Shell } from "./components/Shell";
import { CockpitPrototype } from "./components/CockpitPrototype";
import { HomePage } from "./pages/HomePage";
import { ConfigPage } from "./pages/ConfigPage";
import { DiscoverPage } from "./pages/DiscoverPage";
import { TasksPage } from "./pages/TasksPage";
import { InboxPage } from "./pages/InboxPage";
import { ClinicPage } from "./pages/ClinicPage";
import { AuditPage } from "./pages/AuditPage";
import { HumanQueuePage } from "./pages/HumanQueuePage";
import { ReviewsPage } from "./pages/ReviewsPage";
import { IntegrationsPage } from "./pages/IntegrationsPage";
import { getUiMode, setUiMode } from "./lib/ui-mode";
import { t } from "./lib/i18n";

/** 旧侧栏逃生舱；主入口为舰桥；两套 UI 共用同一套 API */
const NAV = [
  { to: "/", labelKey: "cockpitUi" as const },
  { to: "/legacy", labelKey: "legacyUi" as const, end: true },
  { to: "/discover", label: "发现" },
  { to: "/tasks", label: "任务" },
  { to: "/inbox", label: "Inbox" },
  { to: "/clinic", label: "诊所" },
  { to: "/audit", label: "审计" },
  { to: "/human-queue", label: "人机" },
  { to: "/reviews", label: "Reviews" },
  { to: "/integrations", label: "集成" },
  { to: "/config", label: "配置" },
] as const;

function UiModeSwitch({ mode }: { mode: "cockpit" | "legacy" }) {
  const nav = useNavigate();
  return (
    <div className="mb-3 flex flex-wrap gap-2 px-3">
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
              end={"end" in item ? item.end : false}
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
        </>
      }
    >
      <Routes>
        <Route path="/legacy" element={<HomePage />} />
        <Route path="/showcase" element={<Navigate to="/" replace />} />
        <Route path="/config" element={<ConfigPage variant="full" />} />
        <Route path="/integrations" element={<IntegrationsPage />} />
        <Route path="/discover" element={<DiscoverPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/clinic" element={<ClinicPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/human-queue" element={<HumanQueuePage />} />
        <Route path="/reviews" element={<ReviewsPage />} />
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
          className="rounded border border-rail bg-hull/90 px-3 py-1.5 font-mono text-xs text-frost shadow"
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
  return (
    <Routes>
      <Route path="/" element={<CockpitEntry />} />
      <Route path="/cockpit" element={<CockpitEntry />} />
      <Route path="/*" element={<LegacyApp />} />
    </Routes>
  );
}
