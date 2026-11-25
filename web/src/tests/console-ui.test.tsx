// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { ConsoleTabs, useTabParam } from "../components/console/ConsoleTabs";
import { ConsoleToastHub, pushToast } from "../components/console/ConsoleToastHub";

afterEach(cleanup);

function TabProbe() {
  const [tab, setTab] = useTabParam(["all", "mine", "approvals"] as const, "all");
  const location = useLocation();
  return (
    <div>
      <ConsoleTabs
        tabs={[
          { key: "all", label: "全部" },
          { key: "mine", label: "我的" },
          { key: "approvals", label: "审批" },
        ]}
        value={tab}
        onChange={setTab}
      />
      <output data-testid="location">{location.search}</output>
    </div>
  );
}

describe("ConsoleTabs", () => {
  it("页签写入 URL 且保留可分享状态", () => {
    render(
      <MemoryRouter initialEntries={["/console/tasks"]}>
        <TabProbe />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("tab", { name: "审批" }));
    expect(screen.getByTestId("location").textContent).toBe("?tab=approvals");
    expect(screen.getByRole("tab", { name: "审批" }).getAttribute("aria-selected")).toBe("true");
  });

  it("未知 tab 回落到默认页签", () => {
    render(
      <MemoryRouter initialEntries={["/console/tasks?tab=unknown"]}>
        <TabProbe />
      </MemoryRouter>,
    );
    expect(screen.getByRole("tab", { name: "全部" }).getAttribute("aria-selected")).toBe("true");
  });
});

describe("ConsoleToastHub", () => {
  it("订阅全局 toast 事件并可关闭", () => {
    render(<ConsoleToastHub />);
    act(() => pushToast("保存失败", "error"));
    expect(screen.getByRole("status").textContent).toContain("保存失败");
    fireEvent.click(screen.getByLabelText("关闭提示"));
    expect(screen.queryByRole("status")).toBeNull();
  });
});
