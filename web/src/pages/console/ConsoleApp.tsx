import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ConsoleLayout, ConsoleNavItem } from "../../components/console/ConsoleLayout";
import { api, setToken } from "../../lib/api";
import { ConsoleAccess, useConsoleAccess, useStaffHeartbeat } from "../../lib/console-access";
import { ConsoleOverviewPage } from "./ConsoleOverviewPage";
import { ConsoleCollabPage } from "./ConsoleCollabPage";
import { ConsoleAgentsPage } from "./ConsoleAgentsPage";
import { ConsoleWorkflowsPage } from "./ConsoleWorkflowsPage";
import { ConsoleSkillsPage } from "./ConsoleSkillsPage";
import { ConsoleStaffPage } from "./ConsoleStaffPage";
import { ConsoleTeamsPage } from "./ConsoleTeamsPage";
import { ConsoleApprovalsPage } from "./ConsoleApprovalsPage";
import { ConsoleMessagesPage } from "./ConsoleMessagesPage";
import { ConsoleTasksPage } from "./ConsoleTasksPage";
import { ConsoleSetupPage } from "./ConsoleSetupPage";
import { ConsoleMetricsPage } from "./ConsoleMetricsPage";
import { ConsoleAuditPage } from "./ConsoleAuditPage";
import { ConsoleIntegrationsPage } from "./ConsoleIntegrationsPage";

function ConsoleAccessGate({ access }: { access: ConsoleAccess }) {
  const [tokenInput, setTokenInput] = useState("");
  const [submitted, setSubmitted] = useState(false);

  if (access.state === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-abyss font-mono text-xs text-mute">
        正在校验管理权限…
      </div>
    );
  }

  if (access.state === "setup") {
    return (
      <main className="min-h-screen bg-abyss px-6 py-8 text-frost">
        <div className="mx-auto max-w-5xl">
          <ConsoleSetupPage />
        </div>
      </main>
    );
  }

  const unavailable = access.state === "unavailable";
  const unauthenticated = access.state === "unauthenticated";
  const title = unavailable
    ? "管理服务不可用"
    : unauthenticated
      ? "登录管理中心"
      : "无权访问管理中心";
  const description = unavailable
    ? "无法连接后端服务，请确认服务已启动后重试。"
    : unauthenticated
      ? "请输入超级管理员或管理者的 Bearer Token。"
      : "管理中心仅对超级管理员与管理者开放。";

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-abyss px-6 text-frost">
      <p className="font-display text-lg">{title}</p>
      <p className="text-xs text-mute">{description}</p>
      {unavailable && (
        <button type="button" className="hud-btn text-xs" onClick={access.retry}>
          重新连接
        </button>
      )}
      {unauthenticated && (
        <form
          className="flex w-full max-w-md gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (!tokenInput.trim()) return;
            setSubmitted(true);
            setToken(tokenInput.trim());
          }}
        >
          <input
            type="password"
            className="min-w-0 flex-1 rounded border border-rail bg-hull px-3 py-2 font-mono text-xs text-frost"
            placeholder="API Token"
            value={tokenInput}
            onChange={(event) => {
              setTokenInput(event.target.value);
              setSubmitted(false);
            }}
          />
          <button type="submit" className="hud-btn text-xs">
            登录
          </button>
        </form>
      )}
      {unauthenticated && submitted && (
        <p className="text-xs text-flare">Token 无效或已过期，请重新输入。</p>
      )}
      <div className="flex gap-2">
        {unauthenticated && (
          <a
            href="/join"
            className="rounded border border-rail px-3 py-1.5 text-xs text-mute transition hover:text-frost"
          >
            提交入伙申请
          </a>
        )}
        <a
          href="/twin"
          className="rounded border border-rail px-3 py-1.5 text-xs text-mute transition hover:text-frost"
        >
          孪生大屏
        </a>
      </div>
    </div>
  );
}

/** 管理中心：仅超管与管理者可见，设置向导与员工开关只给超管。 */
export function ConsoleApp() {
  const access = useConsoleAccess();
  const employeeId = access.employeeId;
  const [loggingOut, setLoggingOut] = useState(false);

  useStaffHeartbeat(employeeId, access.state === "allowed");

  if (access.state !== "allowed") {
    return <ConsoleAccessGate access={access} />;
  }

  const isSuper = access.superAdmin;
  const can = (capability: string) => isSuper || access.capabilities.includes(capability);
  const canAny = (capabilities: string[]) =>
    isSuper || capabilities.some((item) => access.capabilities.includes(item));
  const systemConfig = can("system_config");
  const canReadLog = isSuper || can("log_read") || can("console_admin");

  // 导航与路由按能力过滤；无权限的地址会落到 * 后回到概览
  const nav = {
    collab: canAny(["console_admin", "task_dispatch", "message_send"]),
    staff: canAny(["employee_invite", "org_manage"]),
    teams: can("org_manage"),
    tasks: canAny(["task_create", "task_dispatch"]),
    approvals: can("hitl_resolve"),
    messages: canAny(["message_read", "log_read"]),
    agents: canAny(["org_manage", "agent_deregister"]),
    workflows: canAny(["workflow_create", "workflow_modify"]),
    metrics: canReadLog,
    audit: canReadLog,
    integrations: systemConfig,
  };

  async function logout() {
    setLoggingOut(true);
    try {
      await api("/api/identity/logout", { method: "POST" });
    } finally {
      // 无论后端成功、Token 已失效或网络失败，都清掉本地会话并回到门槛
      setToken("");
      setLoggingOut(false);
      access.retry();
    }
  }

  return (
    <ConsoleLayout
      onLogout={() => void logout()}
      logoutBusy={loggingOut}
      nav={
        <>
          <ConsoleNavItem to="/console" icon="◱" label="概览" />
          {nav.collab && <ConsoleNavItem to="/console/collab" icon="⇄" label="协同管理" />}
          {nav.staff && <ConsoleNavItem to="/console/staff" icon="☗" label="员工与入伙" />}
          {nav.teams && <ConsoleNavItem to="/console/teams" icon="⌗" label="团队与工位" />}
          {nav.tasks && <ConsoleNavItem to="/console/tasks" icon="▤" label="任务" />}
          {nav.approvals && <ConsoleNavItem to="/console/approvals" icon="✓" label="审批中心" />}
          {nav.messages && <ConsoleNavItem to="/console/messages" icon="✉" label="消息与追迹" />}
          {nav.agents && <ConsoleNavItem to="/console/agents" icon="◈" label="Agent 与岗位" />}
          {nav.workflows && <ConsoleNavItem to="/console/workflows" icon="⛓" label="工作流模板" />}
          {nav.metrics && <ConsoleNavItem to="/console/metrics" icon="◫" label="指标与报表" />}
          {nav.audit && <ConsoleNavItem to="/console/audit" icon="⚑" label="审计与告警" />}
          {nav.integrations && (
            <ConsoleNavItem to="/console/integrations" icon="⚓" label="集成" />
          )}
          {systemConfig && <ConsoleNavItem to="/console/skills" icon="✦" label="技能包" />}
          {isSuper && <ConsoleNavItem to="/console/setup" icon="⚙" label="设置向导" />}
        </>
      }
    >
      {/* splat 父路由内用相对路径（绝对路径在此不匹配 → 空白页） */}
      <Routes>
        <Route index element={<ConsoleOverviewPage />} />
        {nav.collab && <Route path="collab" element={<ConsoleCollabPage can={can} />} />}
        {nav.staff && <Route path="staff" element={<ConsoleStaffPage superAdmin={isSuper} can={can} />} />}
        {nav.teams && <Route path="teams" element={<ConsoleTeamsPage can={can} />} />}
        {nav.tasks && <Route path="tasks" element={<ConsoleTasksPage can={can} />} />}
        {nav.approvals && <Route path="approvals" element={<ConsoleApprovalsPage can={can} />} />}
        {nav.messages && <Route path="messages" element={<ConsoleMessagesPage can={can} />} />}
        {nav.agents && <Route path="agents" element={<ConsoleAgentsPage can={can} />} />}
        {nav.workflows && <Route path="workflows" element={<ConsoleWorkflowsPage can={can} />} />}
        {nav.metrics && <Route path="metrics" element={<ConsoleMetricsPage can={can} />} />}
        {nav.audit && <Route path="audit" element={<ConsoleAuditPage />} />}
        {systemConfig && (
          <Route path="skills" element={<ConsoleSkillsPage can={can} />} />
        )}
        {nav.integrations && (
          <Route path="integrations" element={<ConsoleIntegrationsPage can={can} />} />
        )}
        {isSuper && <Route path="setup" element={<ConsoleSetupPage />} />}
        <Route path="*" element={<Navigate to="/console" replace />} />
      </Routes>
    </ConsoleLayout>
  );
}
