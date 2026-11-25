import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ConsoleApp } from "../pages/console/ConsoleApp";
import { ConsoleAgentsPage } from "../pages/console/ConsoleAgentsPage";
import { ConsoleOverviewPage } from "../pages/console/ConsoleOverviewPage";
import { ConsoleWorkflowsPage } from "../pages/console/ConsoleWorkflowsPage";
import { ConsoleCollabPage } from "../pages/console/ConsoleCollabPage";
import { ConsoleStaffApplyPage } from "../pages/console/ConsoleStaffPage";
import { isServiceUnavailable } from "../lib/console-access";
import { LEGACY_REDIRECTS } from "../lib/navigation";
import { can, canAny } from "../lib/permissions";

const accessMock = vi.hoisted(() => ({
  current: {
    state: "loading",
    superAdmin: false,
    permissions: [] as string[],
    dataScope: "self",
    can: (_permission: string): boolean => false,
    canAny: (_permissions: string[]): boolean => false,
    retry: () => undefined,
  },
}));

vi.mock("../lib/console-access", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/console-access")>();
  return { ...actual, useConsoleAccess: () => accessMock.current };
});

function renderConsole(
  state: string,
  permissions: string[] = [],
  path = "/console",
) {
  accessMock.current = {
    state,
    superAdmin: permissions.includes("*") || permissions.includes("console_admin"),
    permissions,
    dataScope: "self",
    can: (permission: string) => can(permissions, permission as never),
    canAny: (targets: string[]) => canAny(permissions, targets as never),
    retry: () => undefined,
  };
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/console/*" element={<ConsoleApp />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("管理端访问状态", () => {
  it("首次初始化只开放设置向导", () => {
    const html = renderConsole("setup");
    expect(html).toContain("设置向导");
    expect(html).toContain("超级管理员");
  });

  it("已初始化但未登录时提供 Token 入口", () => {
    const html = renderConsole("unauthenticated");
    expect(html).toContain("登录管理中心");
    expect(html).toContain("API Token");
  });

  it("服务不可用时提供重连入口", () => {
    const html = renderConsole("unavailable");
    expect(html).toContain("管理服务不可用");
    expect(html).toContain("重新连接");
  });

  it("网络错误和代理 5xx 都识别为服务不可用", () => {
    expect(isServiceUnavailable(0)).toBe(true);
    expect(isServiceUnavailable(500)).toBe(true);
    expect(isServiceUnavailable(502)).toBe(true);
    expect(isServiceUnavailable(401)).toBe(false);
    expect(isServiceUnavailable(403)).toBe(false);
  });
});

describe("登录员工的导航可见性", () => {
  it("任何有效登录员工都能进入控制台并看到基础页面", () => {
    const html = renderConsole("allowed", []);
    expect(html).toContain("工作台");
    expect(html).toContain("概览");
    expect(html).toContain("任务中心");
    expect(html).toContain("工作流模板");
    expect(html).not.toContain('href="/console/collab"');
    expect(html).not.toContain('href="/console/organization"');
  });

  it("只读权限只多出消息入口", () => {
    const html = renderConsole("allowed", ["message_read"]);
    expect(html).toContain("消息与追迹");
    expect(html).not.toContain("协同大屏");
    expect(html).not.toContain("审计与告警");
  });

  it("业务权限决定组织/Agent/消息分组", () => {
    const html = renderConsole("allowed", [
      "employee_invite",
      "org_manage",
      "task_dispatch",
      "workflow_create",
      "message_read",
    ]);
    expect(html).toContain("组织");
    expect(html).toContain("Agent 与接入");
    expect(html).toContain("消息与追迹");
    expect(html).not.toContain('href="/console/skills"');
    expect(html).not.toContain('href="/console/collab"');
  });

  it("console_admin 等价全部权限并显示退出入口", () => {
    const html = renderConsole("allowed", ["console_admin"]);
    expect(html).toContain("协同大屏");
    expect(html).toContain("组织");
    expect(html).toContain("技能包");
    expect(html).toContain("集成");
    expect(html).toContain("设置向导");
    expect(html).toContain("审计与告警");
    expect(html).toContain("退出登录");
  });

  it("system_config 只开放系统配置页面", () => {
    const html = renderConsole("allowed", ["system_config"]);
    expect(html).toContain("技能包");
    expect(html).toContain("集成");
    expect(html).toContain("设置向导");
    expect(html).not.toContain('href="/console/organization"');
  });
});

describe("路由与权限门禁", () => {
  it("旧控制台地址映射到组织页签", () => {
    expect(LEGACY_REDIRECTS).toContainEqual([
      "/console/staff",
      "/console/organization?tab=staff",
    ]);
    const html = renderConsole("allowed", ["org_manage"], "/console/organization");
    expect(html).toContain("组织");
    expect(html).toContain("员工");
  });

  it("旧审批地址映射到任务页签", () => {
    expect(LEGACY_REDIRECTS).toContainEqual([
      "/console/approvals",
      "/console/tasks?tab=approvals",
    ]);
    const html = renderConsole("allowed", [], "/console/tasks");
    expect(html).toContain("任务");
  });

  it("直接访问无权限页面渲染统一 403 而非清空整站", () => {
    const html = renderConsole("allowed", ["message_read"], "/console/collab");
    expect(html).toContain("无权访问");
    expect(html).toContain("任务中心");
  });
});

describe("新契约页面", () => {
  it("提供无需登录的员工入伙申请入口", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ConsoleStaffApplyPage />
      </MemoryRouter>,
    );
    expect(html).toContain("员工入伙申请");
    expect(html).toContain("提交申请");
    expect(html).toContain("等待管理员审核");
  });

  it("概览只展示 overview 已有指标", () => {
    const html = renderToStaticMarkup(<ConsoleOverviewPage />);
    expect(html).toContain("当前工作负载");
    expect(html).toContain("组织与实体规模");
    expect(html).not.toContain("metrics-manifest");
    expect(html).not.toContain("内置身份");
  });

  it("Agent 页移除旧 inputs schema 编辑器", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ConsoleAgentsPage can={() => true} />
      </MemoryRouter>,
    );
    expect(html).toContain("Agent");
    expect(html).not.toContain("inputs schema");
    expect(html).not.toContain("role_type");
  });

  it("工作流页使用定义和节点版本模型", () => {
    const html = renderToStaticMarkup(<ConsoleWorkflowsPage can={() => true} />);
    // 骨架屏阶段只显示标题和加载态；检查关键标识字符串
    expect(html).toContain("工作流");
    expect(html).not.toContain("llm_policy");
    expect(html).not.toContain("phases");
    expect(html).not.toContain("gates");
  });

  it("协同页提供结对、协同消息与大屏遥控，不出现模拟数据", () => {
    const html = renderToStaticMarkup(<ConsoleCollabPage can={() => true} />);
    expect(html).toContain("结对协同");
    expect(html).toContain("大屏遥控");
    expect(html).toContain("协同管理");
    expect(html).not.toContain("OFFICE");
    expect(html).not.toContain("/api/collab/pairs/seed");
  });
});
