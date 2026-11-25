import { Navigate, Route, Routes } from "react-router-dom";
import { ConsoleToastHub } from "./components/console/ConsoleToastHub";
import { ConsoleApp } from "./pages/console/ConsoleApp";
import { ConsoleStaffApplyPage } from "./pages/console/ConsoleStaffPage";
import { TwinPage } from "./twin/TwinPage";
import { LEGACY_REDIRECTS } from "./lib/navigation";

// 控制台内的旧地址由 ConsoleApp 处理；这里只保留顶层旧入口。
const TOP_LEVEL_REDIRECTS = LEGACY_REDIRECTS.filter(([from]) => !from.startsWith("/console/"));

export default function App() {
  return (
    <>
      <ConsoleToastHub />
      <Routes>
        <Route path="/" element={<Navigate to="/console" replace />} />
        <Route path="/console/*" element={<ConsoleApp />} />
        <Route path="/join" element={<ConsoleStaffApplyPage />} />
        <Route path="/twin" element={<TwinPage />} />
        {TOP_LEVEL_REDIRECTS.map(([from, to]) => (
          <Route key={from} path={from} element={<Navigate to={to} replace />} />
        ))}
        <Route path="*" element={<Navigate to="/console" replace />} />
      </Routes>
    </>
  );
}
