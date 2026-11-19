import { Navigate, Route, Routes } from "react-router-dom";
import { WriteFailToast } from "./components/WriteFailToast";
import { ConsoleApp } from "./pages/console/ConsoleApp";
import { ConsoleStaffApplyPage } from "./pages/console/ConsoleStaffPage";
import { TwinPage } from "./twin/TwinPage";

const LEGACY_REDIRECTS: Array<[string, string]> = [
  ["/collab", "/console/collab"],
  ["/staff", "/console/staff"],
  ["/teams", "/console/teams"],
  ["/tasks", "/console/tasks"],
  ["/approvals", "/console/approvals"],
  ["/messages", "/console/messages"],
  ["/inbox", "/console/messages"],
  ["/agents", "/console/agents"],
  ["/workflows", "/console/workflows"],
  ["/metrics", "/console/metrics"],
  ["/audit", "/console/audit"],
  ["/integrations", "/console/integrations"],
  ["/skills", "/console/skills"],
  ["/setup", "/console/setup"],
];

export default function App() {
  return (
    <>
      <WriteFailToast />
      <Routes>
        <Route path="/" element={<Navigate to="/console" replace />} />
        <Route path="/console/*" element={<ConsoleApp />} />
        <Route path="/join" element={<ConsoleStaffApplyPage />} />
        <Route path="/twin" element={<TwinPage />} />
        {LEGACY_REDIRECTS.map(([from, to]) => (
          <Route key={from} path={from} element={<Navigate to={to} replace />} />
        ))}
        <Route path="*" element={<Navigate to="/console" replace />} />
      </Routes>
    </>
  );
}
