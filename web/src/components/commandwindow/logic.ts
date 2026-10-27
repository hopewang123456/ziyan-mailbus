/** 发令窗口纯逻辑（从组件提取以便单测；D13 验收承诺的最小测试覆盖） */
import type { InputField, Position } from "./PositionPicker";
import type { DraftStep } from "./DraftPreview";

export type FormValues = Record<string, string | number | boolean>;

export function defaults(fields: InputField[]): FormValues {
  const v: FormValues = {};
  for (const f of fields) if (f.default !== undefined) v[f.name] = f.default;
  return v;
}

export function missingRequired(fields: InputField[], values: FormValues): string[] {
  return fields.filter((f) => f.required && !String(values[f.name] ?? "").trim()).map((f) => f.label?.zh || f.name);
}

export function buildIntent(p: Position | null, values: FormValues): string {
  if (!p) return "";
  const main =
    String(values.topic ?? values.task ?? "").trim() ||
    Object.values(values).map(String).find((s) => s.trim()) ||
    `${p.name_zh}任务`;
  const base = defaults(p.inputs || []);
  const extras = Object.entries(values)
    .filter(
      ([k, v]) =>
        v !== "" && v !== undefined && !["topic", "task", "pin_agent"].includes(k) && v !== base[k],
    )
    .map(([k, v]) => `${k}=${v}`)
    .join("；");
  return extras ? `${main}（${extras}）` : main;
}

export function newTaskId(): string {
  return `cmd-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

/** 选职位单步发令的 v3 envelope（P1 提交链路的唯一构造点） */
export function singleStepEnvelope(
  selected: Position,
  intent: string,
  formValues: FormValues,
  taskId: string,
): Record<string, unknown> {
  return {
    task_id: taskId,
    intent,
    initiator: "ziyan", // D2 内置主仓角色（一期字符串，二期真节点身份）
    task_type: "custom",
    tier: "M",
    mode: "explicit", // D3：选了职位 = 指定首步角色；未 pin_agent 时派发器空闲优先
    planned_chain: [
      {
        role_type: selected.role_type,
        reason: `子言经发令窗口指派：${selected.name_zh}`,
        ...(formValues.pin_agent ? { pin_agent: String(formValues.pin_agent) } : {}),
      },
    ],
    artifacts_in: [],
    extensions: { mailbus: { command_window: { form: formValues, position: selected.key } } },
  };
}

/** LLM 草稿确认后的多步 envelope（D4） */
export function draftEnvelope(
  requirement: string,
  steps: DraftStep[],
  taskId: string,
): Record<string, unknown> {
  return {
    task_id: taskId,
    intent: requirement,
    initiator: "ziyan",
    task_type: "custom",
    tier: "M",
    mode: "explicit",
    planned_chain: steps.map((s) => ({ role_type: s.role_type, reason: s.reason })),
    artifacts_in: [],
    extensions: { mailbus: { command_window: { via: "llm_draft", steps: steps.length } } },
  };
}

/** 工作流模板（交接③）：phases[].steps[].role_type 拉平为职位链。 */
export type WorkflowTemplate = {
  id: string;
  display?: { zh?: string; en?: string };
  phases?: Array<{ id?: string; display?: { zh?: string }; steps?: Array<{ node_type?: string; role_type?: number }> }>;
};

export function templateSteps(wf: WorkflowTemplate): DraftStep[] {
  const out: DraftStep[] = [];
  for (const ph of wf.phases || []) {
    const reason = ph.display?.zh || ph.id || wf.display?.zh || "";
    for (const st of ph.steps || []) {
      if (typeof st.role_type === "number") out.push({ role_type: st.role_type, reason });
    }
  }
  return out;
}

/** 模板起草 envelope：extensions 顶层点号键 `mailbus.workflow` 绑定 workflow_id
 *  （python resolve_workflow_id/engine 的消费形状）。 */
export function templateEnvelope(
  requirement: string,
  steps: DraftStep[],
  taskId: string,
  workflowId: string,
): Record<string, unknown> {
  const env = draftEnvelope(requirement, steps, taskId);
  const ext = env.extensions as Record<string, unknown>;
  ext["mailbus.workflow"] = { workflow_id: workflowId };
  const mailbus = ext.mailbus as Record<string, unknown>;
  mailbus.command_window = { via: "template", workflow_id: workflowId, steps: steps.length };
  return env;
}
