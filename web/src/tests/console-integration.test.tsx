import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ConsoleApp } from "../pages/console/ConsoleApp";
import { ConsoleAgentsPage } from "../pages/console/ConsoleAgentsPage";
import { ConsoleOverviewPage } from "../pages/console/ConsoleOverviewPage";
import { ConsoleWorkflowsPage } from "../pages/console/ConsoleWorkflowsPage";
import { ConsoleCollabPage } from "../pages/console/ConsoleCollabPage";
import { ConsoleStaffApplyPage } from "../pages/console/ConsoleStaffPage";
import { isServiceUnavailable } from "../lib/console-access";

const accessMock = vi.hoisted(() => ({
  current: {
    state: "loading",
    superAdmin: false,
    capabilities: [] as string[],
    retry: () => undefined,
  },
}));

vi.mock("../lib/console-access", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/console-access")>();
  return { ...actual, useConsoleAccess: () => accessMock.current };
});

function renderConsole(state: string, capabilities: string[] = []) {
  accessMock.current = {
    state,
    superAdmin: capabilities.includes("*"),
    capabilities,
    retry: () => undefined,
  };
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={["/console"]}>
      <ConsoleApp />
    </MemoryRouter>,
  );
}

describe("管理端访问状态", () => {
  it("首次初始化只开放设置向导", () => {
    const html = renderConsole("setup");
    expect(html).toContain("设置向导");
    expect(html).toContain("超级管理员");
    expect(html).not.toContain("无权访问管理中心");
  });

  it("已初始化但未登录时提供 Token 入口", () => {
    const html = renderConsole("unauthenticated");
    expect(html).toContain("登录管理中心");
    expect(html).toContain("API Token");
  });

  it("服务不可用与无权限分开显示", () => {
    expect(renderConsole("unavailable")).toContain("管理服务不可用");
    expect(renderConsole("unavailable")).toContain("重新连接");
    expect(renderConsole("denied", ["message_read"])).toContain("无权访问管理中心");
  });

  it("网络错误和代理 5xx 都识别为服务不可用", () => {
    expect(isServiceUnavailable(0)).toBe(true);
    expect(isServiceUnavailable(500)).toBe(true);
    expect(isServiceUnavailable(502)).toBe(true);
    expect(isServiceUnavailable(401)).toBe(false);
    expect(isServiceUnavailable(403)).toBe(false);
  });

  it("普通管理者只看到能力范围内的页面", () => {
    const html = renderConsole("allowed", ["console_admin", "log_read"]);
    expect(html).toContain("指标与报表");
    expect(html).toContain("审计与告警");
    expect(html).toContain("协同管理");
    expect(html).not.toContain("员工与入伙");
    expect(html).not.toContain("工作流模板");
    expect(html).not.toContain("设置向导");
    expect(html).not.toContain("技能包");
    expect(html).not.toContain("诊所");
    expect(html).not.toContain("协调台");
  });

  it("具备业务能力的管理者可见对应页面", () => {
    const html = renderConsole("allowed", [
      "console_admin",
      "employee_invite",
      "org_manage",
      "task_dispatch",
      "workflow_create",
      "message_read",
    ]);
    expect(html).toContain("员工与入伙");
    expect(html).toContain("团队与工位");
    expect(html).toContain("任务");
    expect(html).toContain("工作流模板");
    expect(html).toContain("Agent 与岗位");
    expect(html).not.toContain("技能包");
  });

  it("超管可见系统配置页面并提供退出入口", () => {
    const html = renderConsole("allowed", ["*"]);
    expect(html).toContain("指标与报表");
    expect(html).toContain("审计与告警");
    expect(html).toContain("技能包");
    expect(html).toContain("集成");
    expect(html).toContain("设置向导");
    expect(html).toContain("退出登录");
    expect(html).not.toContain("/api/identities");
  });

  it("系统配置权限可见技能包与集成", () => {
    const html = renderConsole("allowed", ["console_admin", "system_config"]);
    expect(html).toContain("技能包");
    expect(html).toContain("集成");
    expect(html).not.toContain("设置向导");
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
    const html = renderToStaticMarkup(<ConsoleAgentsPage can={() => true} />);
    expect(html).toContain("Agent 与岗位");
    expect(html).not.toContain("inputs schema");
    expect(html).not.toContain("role_type");
  });

  it("工作流页使用定义和节点版本模型", () => {
    const html = renderToStaticMarkup(<ConsoleWorkflowsPage can={() => true} />);
    expect(html).toContain("新工作流名称");
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
