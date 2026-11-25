import { Suspense, lazy, useState } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { ConsoleLayout } from "../../components/console/ConsoleLayout";
import { ConsolePageState } from "../../components/console/ConsolePageState";
import { RequirePermission } from "../../components/console/RequirePermission";
import { api, setToken } from "../../lib/api";
import { ConsoleAccess, useConsoleAccess, useStaffHeartbeat } from "../../lib/console-access";
import { visibleNavGroups } from "../../lib/navigation";
import type { Permission } from "../../lib/permissions";
import { ConsoleOverviewPage } from "./ConsoleOverviewPage";
import { ConsoleCollabPage } from "./ConsoleCollabPage";
import { ConsoleAgentsPage } from "./ConsoleAgentsPage";
import { ConsoleOrganizationPage } from "./ConsoleOrganizationPage";
import { ConsoleWorkflowsPage } from "./ConsoleWorkflowsPage";
import { ConsoleSkillsPage } from "./ConsoleSkillsPage";
import { ConsoleMessagesPage } from "./ConsoleMessagesPage";
import { ConsoleTasksPage } from "./ConsoleTasksPage";
import { ConsoleSetupPage } from "./ConsoleSetupPage";
import { ConsoleMetricsPage } from "./ConsoleMetricsPage";
import { ConsoleAuditPage } from "./ConsoleAuditPage";
import { ConsoleIntegrationsPage } from "./ConsoleIntegrationsPage";

const WorkflowEditorPage = lazy(() => import("./WorkflowEditorPage").then((m) => ({ default: m.WorkflowEditorPage })));
const ConsoleTaskDetailPage = lazy(() => import("./ConsoleTaskDetailPage").then((m) => ({ default: m.ConsoleTaskDetailPage })));

function TaskDetailRoute({ can }: { can: (capability: string) => boolean }) {
  return (
    <Suspense fallback={<ConsolePageState kind="loading" title="加载任务详情" description="首次加载…" />}>
      <ConsoleTaskDetailPage can={can} />
    </Suspense>
  );
}

function WorkflowEditorRoute({ can }: { can: (capability: string) => boolean }) {
  const { workflow_id, version } = useParams();
  const wid = workflow_id ?? "";
  const ver = version ? Number(version) : null;
  if (!wid || ver === null || Number.isNaN(ver)) {
    return <Navigate to="/console/workflows" replace />;
  }
  return (
    <Suspense fallback={<ConsolePageState kind="loading" title="加载编辑器" description="首次加载 React Flow…" />}>
      <WorkflowEditorPage
        workflowId={wid}
        version={ver}
        canModify={can("workflow_modify")}
        canPublish={can("workflow_publish")}
      />
    </Suspense>
  );
}

function ConsoleAccessGate({ access }: { access: ConsoleAccess }) {
  const [tokenInput, setTokenInput] = useState("");
  const [submitted, setSubmitted] = useState(false);

  if (access.state === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-abyss font-mono text-xs text-mute">
        正在校验登录身份…
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
  const title = unavailable ? "管理服务不可用" : "登录管理中心";
  const description = unavailable
    ? "无法连接后端服务，请确认服务已启动后重试。"
    : "请输入有效员工的 Bearer Token。";

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-abyss px-6 text-frost">
      <p className="font-display text-lg">{title}</p>
      <p className="text-xs text-mute">{description}</p>
      {unavailable && (
        <button type="button" className="hud-btn text-xs" onClick={access.retry}>
          重新连接
        </button>
      )}
      {!unavailable && (
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
      {!unavailable && submitted && (
        <p className="text-xs text-flare">Token 无效或已过期，请重新输入。</p>
      )}
      <div className="flex gap-2">
        {!unavailable && (
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

/** 管理中心：所有有效登录员工可进入；页面与按钮按权限点过滤。 */
export function ConsoleApp() {
  const access = useConsoleAccess();
  const employeeId = access.employeeId;
  const [loggingOut, setLoggingOut] = useState(false);

  useStaffHeartbeat(employeeId, access.state === "allowed");

  if (access.state !== "allowed") {
    return <ConsoleAccessGate access={access} />;
  }

  const can = (permission: string) => access.can(permission as Permission);
  const groups = visibleNavGroups(access.permissions);

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
    <ConsoleLayout groups={groups} onLogout={() => void logout()} logoutBusy={loggingOut}>
      <Routes>
        <Route index element={<ConsoleOverviewPage />} />
        <Route path="metrics" element={<ConsoleMetricsPage can={can} />} />
        <Route path="tasks" element={<ConsoleTasksPage can={can} />} />
        <Route path="tasks/:task_id" element={<TaskDetailRoute can={can} />} />
        <Route
          path="messages"
          element={
            <RequirePermission anyOf={["message_read"]}>
              <ConsoleMessagesPage can={can} />
            </RequirePermission>
          }
        />
        <Route
          path="collab"
          element={
            <RequirePermission anyOf={["console_admin"]}>
              <ConsoleCollabPage can={can} />
            </RequirePermission>
          }
        />
        <Route
          path="organization"
          element={
            <RequirePermission anyOf={["org_manage", "employee_invite", "role_manage"]}>
              <ConsoleOrganizationPage can={can} />
            </RequirePermission>
          }
        />
        <Route path="workflows" element={<ConsoleWorkflowsPage can={can} />} />
        <Route
          path="workflows/:workflow_id/v/:version"
          element={
            <RequirePermission anyOf={["workflow_modify", "workflow_publish", "workflow_create"]}>
              <WorkflowEditorRoute can={can} />
            </RequirePermission>
          }
        />
        <Route
          path="skills"
          element={
            <RequirePermission anyOf={["system_config"]}>
              <ConsoleSkillsPage can={can} />
            </RequirePermission>
          }
        />
        <Route
          path="agents"
          element={
            <RequirePermission anyOf={["org_manage", "agent_deregister"]}>
              <ConsoleAgentsPage can={can} />
            </RequirePermission>
          }
        />
        <Route
          path="integrations"
          element={
            <RequirePermission anyOf={["system_config"]}>
              <ConsoleIntegrationsPage can={can} />
            </RequirePermission>
          }
        />
        <Route
          path="audit"
          element={
            <RequirePermission anyOf={["log_read"]}>
              <ConsoleAuditPage />
            </RequirePermission>
          }
        />
        <Route
          path="setup"
          element={
            <RequirePermission anyOf={["system_config"]}>
              <ConsoleSetupPage />
            </RequirePermission>
          }
        />
        {/* 旧地址：控制台内直接重定向，避免多级跳转链 */}
        <Route path="staff" element={<Navigate to="/console/organization?tab=staff" replace />} />
        <Route path="teams" element={<Navigate to="/console/organization?tab=teams" replace />} />
        <Route path="approvals" element={<Navigate to="/console/tasks?tab=approvals" replace />} />
        <Route path="*" element={<Navigate to="/console" replace />} />
      </Routes>
    </ConsoleLayout>
  );
}
