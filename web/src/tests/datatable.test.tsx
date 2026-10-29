import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DataTable, StateChip, fmt, shortTime } from "../components/DataTable";

describe("DataTable", () => {
  const rows = [
    { id: "t-1", intent: "修复登录", status: "running", tier: "M" },
    { id: "t-2", intent: "审查报告", status: "succeeded", tier: "S" },
  ];
  const cols = [
    { key: "id", label: "任务" },
    { key: "intent", label: "意图" },
    { key: "status", label: "状态", render: (r: Record<string, unknown>) => <StateChip state={r.status} /> },
  ];

  it("渲染表头/行/自定义列", () => {
    const html = renderToStaticMarkup(<DataTable rows={rows} cols={cols} />);
    expect(html).toContain("任务");
    expect(html).toContain("修复登录");
    expect(html).toContain("审查报告");
    expect(html).toContain("hud-table-th");
    expect(html).toContain("hud-table-row");
    expect(html).toContain("bg-sky-300"); // running 状态色点
  });

  it("空态与加载态", () => {
    expect(renderToStaticMarkup(<DataTable rows={[]} cols={cols} empty="无任务" />)).toContain("无任务");
    expect(renderToStaticMarkup(<DataTable rows={null} cols={cols} />)).toContain("加载中…");
  });

  it("null 值显示 —", () => {
    const html = renderToStaticMarkup(<DataTable rows={[{ id: "x" }]} cols={[{ key: "note", label: "注" }]} />);
    expect(html).toContain("—");
  });
});

describe("StateChip 色调", () => {
  it("succeeded 绿 / failed 红 / pending 黄", () => {
    expect(renderToStaticMarkup(<StateChip state="succeeded" />)).toContain("bg-emerald-400");
    expect(renderToStaticMarkup(<StateChip state="failed" />)).toContain("bg-rose-400");
    expect(renderToStaticMarkup(<StateChip state="await_plan_approval" />)).toContain("bg-amber-300");
    expect(renderToStaticMarkup(<StateChip state="running" />)).toContain("bg-sky-300");
  });
});

describe("fmt/shortTime", () => {
  it("fmt null/空/数字/对象", () => {
    expect(fmt(null)).toBe("—");
    expect(fmt("")).toBe("—");
    expect(fmt(3)).toBe("3");
    expect(fmt({ a: 1 })).toBe('{"a":1}');
  });
  it("shortTime ISO 截分钟", () => {
    expect(shortTime("2026-10-30T21:04:33+0800")).toBe("2026-10-30 21:04");
    expect(shortTime(null)).toBe("—");
  });
});
