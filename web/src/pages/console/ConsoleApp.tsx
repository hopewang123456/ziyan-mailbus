import { Navigate, Route, Routes } from "react-router-dom";
import { ConsoleLayout, ConsoleNavItem } from "../../components/console/ConsoleLayout";
import { ConsoleOverviewPage } from "./ConsoleOverviewPage";
import { ConsoleAgentsPage } from "./ConsoleAgentsPage";
import { ConsoleMetricsPage } from "./ConsoleMetricsPage";
import { ConsoleWorkflowsPage } from "./ConsoleWorkflowsPage";
import { ConsoleIntegrationsPage } from "./ConsoleIntegrationsPage";
import { ConsoleAuditPage } from "./ConsoleAuditPage";
import { ClinicPage } from "../ClinicPage";

/**
 * 管理中心应用（P3，D6：逃生舱从「降级兜底 UI」升级为「协同管理中心」）。
 *
 * URL：/console（旧的 /legacy 保留为 redirect 兼容历史直链）。
 * 首批页面：概览；后续按 P3 迁移计划增补（配置管理/工作流模板/集成/审计/诊所/效率报表）。
 */
export function ConsoleApp() {
  return (
    <ConsoleLayout
      nav={
        <>
          <ConsoleNavItem to="/console" icon="◱" label="概览" />
          <ConsoleNavItem to="/console/agents" icon="◈" label="Agent 与职位" />
          <ConsoleNavItem to="/console/workflows" icon="⛓" label="工作流模板" />
          <ConsoleNavItem to="/console/integrations" icon="⇄" label="集成" />
          <ConsoleNavItem to="/console/metrics" icon="◴" label="指标与报表" />
          <ConsoleNavItem to="/console/audit" icon="☰" label="审计与告警" />
          <ConsoleNavItem to="/console/clinic" icon="✚" label="诊所" />
        </>
      }
    >
      {/* splat 父路由内用相对路径（绝对路径在此不匹配 → 空白页） */}
      <Routes>
        <Route index element={<ConsoleOverviewPage />} />
        {/* P3 第四批：全部导航项已挂真页面（概览外的七个路由） */}
        <Route path="agents" element={<ConsoleAgentsPage />} />
        <Route path="workflows" element={<ConsoleWorkflowsPage />} />
        <Route path="integrations" element={<ConsoleIntegrationsPage />} />
        <Route path="metrics" element={<ConsoleMetricsPage />} />
        <Route path="audit" element={<ConsoleAuditPage />} />
        <Route path="clinic" element={<ClinicPage />} />
        <Route path="*" element={<Navigate to="/console" replace />} />
      </Routes>
    </ConsoleLayout>
  );
}
