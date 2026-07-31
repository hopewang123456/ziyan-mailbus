import { NavLink, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { HomePage } from "./pages/HomePage";
import { ConfigPage } from "./pages/ConfigPage";
import { DiscoverPage } from "./pages/DiscoverPage";
import { TasksPage } from "./pages/TasksPage";
import { InboxPage } from "./pages/InboxPage";
import { ClinicPage } from "./pages/ClinicPage";
import { AuditPage } from "./pages/AuditPage";
import { HumanQueuePage } from "./pages/HumanQueuePage";
import { ReviewsPage } from "./pages/ReviewsPage";

const NAV = [
  { to: "/", label: "桥", end: true },
  { to: "/config", label: "配置 / Token" },
  { to: "/discover", label: "发现 / Enable" },
  { to: "/tasks", label: "任务" },
  { to: "/inbox", label: "Inbox" },
  { to: "/clinic", label: "诊所" },
  { to: "/audit", label: "审计" },
  { to: "/human-queue", label: "人机队列" },
  { to: "/reviews", label: "Reviews" },
] as const;

export default function App() {
  return (
    <Shell
      nav={NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={"end" in item ? item.end : false}
          className={({ isActive }) =>
            [
              "block rounded-sm px-3 py-2 font-display text-[11px] uppercase tracking-wider transition",
              isActive
                ? "bg-cyan-signal/15 text-cyan-signal shadow-glow"
                : "text-mute hover:bg-rail/60 hover:text-frost",
            ].join(" ")
          }
        >
          {item.label}
        </NavLink>
      ))}
    >
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/config" element={<ConfigPage />} />
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
