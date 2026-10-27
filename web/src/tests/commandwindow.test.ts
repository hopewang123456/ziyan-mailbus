import { describe, expect, it } from "vitest";
import {
  buildIntent,
  defaults,
  draftEnvelope,
  missingRequired,
  singleStepEnvelope,
  templateSteps,
  templateEnvelope,
} from "../components/commandwindow/logic";

/** D13 承诺的最小核心测试：发令窗口纯逻辑（envelope 构造 / 校验 / intent 组装） */

const designer: Parameters<typeof buildIntent>[0] = {
  role_type: 1,
  key: "planner",
  name_zh: "方案设计师",
  name_en: "Planner",
  default_sla_minutes: 30,
  inputs: [
    { name: "topic", label: { zh: "设计主题" }, type: "string", required: true },
    { name: "priority", label: { zh: "优先级" }, type: "enum", options: ["high", "normal"], default: "normal" },
  ],
  candidates: [],
};

describe("defaults / missingRequired", () => {
  it("defaults 填充 schema 默认值", () => {
    expect(defaults(designer.inputs)).toEqual({ priority: "normal" });
  });

  it("missingRequired 抓缺必填（返回中文标签）", () => {
    expect(missingRequired(designer.inputs, {})).toEqual(["设计主题"]);
    expect(missingRequired(designer.inputs, { topic: "缓存方案" })).toEqual([]);
  });
});

describe("buildIntent", () => {
  it("主字段 topic 优先 + 非默认值进括号", () => {
    const intent = buildIntent(designer, { topic: "Redis 设计", priority: "high" });
    expect(intent).toBe("Redis 设计（priority=high）");
  });

  it("默认值不重复进括号", () => {
    const intent = buildIntent(designer, { topic: "Redis 设计", priority: "normal" });
    expect(intent).toBe("Redis 设计");
  });

  it("空表单回退职位名任务", () => {
    expect(buildIntent(designer, {})).toBe("方案设计师任务");
  });
});

describe("envelope 构造（v3 协议）", () => {
  it("单步：explicit + role_type + initiator=ziyan + pin 透传", () => {
    const env = singleStepEnvelope(designer, "Redis 设计", { topic: "Redis 设计", pin_agent: "lingzhao" }, "cmd-t1");
    expect(env.mode).toBe("explicit");
    expect(env.initiator).toBe("ziyan");
    expect(env.planned_chain).toEqual([
      { role_type: 1, reason: "子言经发令窗口指派：方案设计师", pin_agent: "lingzhao" },
    ]);
    expect((env.extensions as Record<string, Record<string, unknown>>).mailbus.command_window).toMatchObject({
      position: "planner",
    });
  });

  it("无 pin 时不带 pin_agent 键", () => {
    const env = singleStepEnvelope(designer, "x", { topic: "x" }, "cmd-t2");
    expect((env.planned_chain as Array<Record<string, unknown>>)[0]).not.toHaveProperty("pin_agent");
  });

  it("草稿多步：按步骤透传 role_type/reason", () => {
    const env = draftEnvelope("调研并验收", [
      { role_type: 3, reason: "调研" },
      { role_type: 12, reason: "验收" },
    ], "cmd-t3");
    expect(env.planned_chain).toHaveLength(2);
    expect(env.planned_chain).toEqual([
      { role_type: 3, reason: "调研" },
      { role_type: 12, reason: "验收" },
    ]);
  });
});

describe("模板起草（交接③）", () => {
  const wf = {
    id: "bugfix_s",
    display: { zh: "小修" },
    phases: [
      { id: "fix", display: { zh: "修复" }, steps: [{ node_type: "agent", role_type: 8 }] },
      { id: "verify", display: { zh: "验收" }, steps: [{ role_type: 12 }, { role_type: 12 }] },
      { id: "empty", steps: [] },
    ],
  };

  it("templateSteps：phases 拉平 + reason 取阶段名", () => {
    expect(templateSteps(wf)).toEqual([
      { role_type: 8, reason: "修复" },
      { role_type: 12, reason: "验收" },
      { role_type: 12, reason: "验收" },
    ]);
  });

  it("templateSteps：空 phases / 无 role_type 步骤 → 空链", () => {
    expect(templateSteps({ id: "x", phases: [] })).toEqual([]);
    expect(templateSteps({ id: "x", phases: [{ id: "p", steps: [{ node_type: "agent" }] }] })).toEqual([]);
  });

  it("templateEnvelope：explicit + workflow_id 绑定进 extensions", () => {
    const env = templateEnvelope("修个 bug", templateSteps(wf), "cmd-t9", "bugfix_s");
    expect(env.mode).toBe("explicit");
    expect(env.planned_chain).toHaveLength(3);
    const ext = env.extensions as Record<string, unknown>;
    // python resolve_workflow_id 消费顶层点号键 mailbus.workflow
    expect(ext["mailbus.workflow"]).toEqual({ workflow_id: "bugfix_s" });
    expect((ext.mailbus as Record<string, unknown>).command_window).toMatchObject({
      via: "template", workflow_id: "bugfix_s",
    });
  });
});
