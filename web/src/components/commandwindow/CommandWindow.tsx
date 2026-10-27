import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../../lib/api";
import { PositionPicker, type Position } from "./PositionPicker";
import { InputSchemaForm } from "./InputSchemaForm";
import { DraftPreview, type DraftStep } from "./DraftPreview";
import { buildIntent, defaults, draftEnvelope, missingRequired, newTaskId, singleStepEnvelope } from "./logic";

/** 一条会话消息（D1 双向窗口：子言发出的指令 / 系统回执 / 被唤起通知） */
type FlowMessage = {
  id: string;
  from: "ziyan" | "system";
  text: string;
  ts: string;
  tone?: "ok" | "error" | "info";
  actions?: Array<{ action: string; label: string; task_id: string }>;
};

/** 被唤起消息（/api/command/inbox 聚合项 → 流消息） */
function toFlowItem(it: {
  source: string;
  id: string;
  ts?: string;
  text?: string;
  tone?: string;
  actions?: Array<{ action: string; label: string; task_id: string }>;
}): FlowMessage {
  const prefix: Record<string, string> = {
    manager_pending: "【待我处理】",
    human_queue: "【待批】",
    alert: "【告警】",
    inbox: "【新消息】",
  };
  return {
    id: it.id,
    from: "system",
    text: `${prefix[it.source] || ""}${it.text || ""}`,
    ts: it.ts || "",
    tone: it.tone === "critical" ? "error" : it.tone === "warn" ? "info" : "info",
    actions: it.actions,
  };
}

export type CommandWindowState = {
  open: boolean;
  setOpen(v: boolean): void;
};

/**
 * 发令交互窗口（P1 第二批）— 全局抽屉。
 *
 * 挂载决策（待确认项 #5 自主拍板）：抽屉而非 HUD 面板 —— 会话流需要跨页面
 * 常驻（HUD 面板切换会卸载组件），且双舱（cockpit/legacy）都要能唤起，
 * 全局浮层是唯一满足 D1「与我交互的窗口」常驻性的形态。
 *
 * 一期（UI 聚合）：起草走 GET /api/positions + inputs 动态表单 →
 * POST /api/tasks/create（v3 A2A Envelope, mode=explicit）；
 * 被唤起消息流二期接子言 inbox 真通道。
 */
export function CommandWindow({ state }: { state: CommandWindowState }) {
  const [positions, setPositions] = useState<Position[]>([]);
  const [selected, setSelected] = useState<Position | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string | number | boolean>>({});
  const [flow, setFlow] = useState<FlowMessage[]>([]);
  const [busy, setBusy] = useState(false);
  // D4 自由起草（LLM 草稿确认制）：requirement → /api/command/draft → 预览调整 → explicit 提交
  const [requirement, setRequirement] = useState("");
  const [draftSteps, setDraftSteps] = useState<DraftStep[] | null>(null);
  // D2/D15 内置身份：显示名可编辑（id 稳定）
  const [identity, setIdentity] = useState<{ id: string; display_name: string } | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  // D1 被唤起：/api/command/inbox 轮询（30s），已展示 id 去重；未读徽标在 CommandWindowButton
  const seenIds = useRef<Set<string>>(new Set());
  const flowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!state.open || identity) return;
    void api<{ identities?: Array<{ id: string; display_name: string }> }>("/api/identities").then((r) => {
      if (r.ok && r.data?.identities?.length) setIdentity(r.data.identities[0]);
    });
  }, [state.open, identity]);

  // 被唤起消息轮询：开窗时拉 + 30s 周期；去重后追加进会话流（D1 中途被唤起可见可响应）
  useEffect(() => {
    if (!state.open) return;
    let alive = true;
    const tick = async () => {
      const r = await api<{
        unread?: number;
        items?: Array<{ id: string; source: string; ts?: string; text?: string; tone?: string; actions?: Array<{ action: string; label: string; task_id: string }> }>;
      }>("/api/command/inbox");
      if (!alive || !r.ok || !r.data) return;
      const fresh = (r.data.items || []).filter((it) => !seenIds.current.has(it.id));
      if (fresh.length) {
        for (const it of fresh) seenIds.current.add(it.id);
        setFlow((f) => [...f, ...fresh.map(toFlowItem)]);
      }
    };
    void tick();
    const timer = window.setInterval(tick, 30000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [state.open]);

  async function runAction(a: { action: string; task_id: string }) {
    const r = await api(`/api/tasks/${encodeURIComponent(a.task_id)}/fsm/${encodeURIComponent(a.action)}`, {
      method: "POST",
      body: JSON.stringify({ reason: "command_window" }),
    });
    setFlow((f) => [
      ...f,
      {
        id: `act-${Date.now()}-${a.action}`,
        from: "system",
        text: r.ok ? `已执行「${a.action}」（${a.task_id}）` : `执行失败「${a.action}」：${r.error}`,
        ts: now(),
        tone: r.ok ? "ok" : "error",
      },
    ]);
    if (r.ok) seenIds.current.clear(); // 动作执行后刷新全部被唤起消息
  }

  async function saveName() {
    if (!identity || !nameDraft.trim()) return setEditingName(false);
    const r = await api<{ identity?: { display_name: string } }>(`/api/identities/${identity.id}`, {
      method: "PATCH",
      body: JSON.stringify({ display_name: nameDraft.trim() }),
    });
    if (r.ok && r.data?.identity) {
      const renamed = r.data.identity;
      setIdentity({ ...identity, display_name: renamed.display_name });
      setFlow((f) => [...f, { id: `n${Date.now()}`, from: "system", text: `身份显示名已改为「${renamed.display_name}」`, ts: now(), tone: "ok" }]);
    }
    setEditingName(false);
  }

  useEffect(() => {
    if (!state.open || positions.length) return;
    void api<{ positions?: Position[] }>("/api/positions").then((r) => {
      if (r.ok && r.data?.positions) setPositions(r.data.positions);
      else if (!r.ok)
        setFlow((f) => [
          ...f,
          { id: `e${Date.now()}`, from: "system", text: `职位目录加载失败：${r.error}`, ts: now(), tone: "error" },
        ]);
    });
  }, [state.open, positions.length]);

  useEffect(() => {
    flowRef.current?.scrollTo({ top: flowRef.current.scrollHeight });
  }, [flow]);

  const intentText = useMemo(() => buildIntent(selected, formValues), [selected, formValues]);

  async function generateDraft() {
    if (!requirement.trim() || busy) return;
    setBusy(true);
    setFlow((f) => [...f, { id: `d${Date.now()}`, from: "ziyan", text: `【自由需求】${requirement.trim()}`, ts: now() }]);
    const r = await api<{ draft?: { planned_chain?: DraftStep[] } }>("/api/command/draft", {
      method: "POST",
      body: JSON.stringify({ intent: requirement.trim() }),
    });
    setBusy(false);
    if (r.ok && r.data?.draft?.planned_chain?.length) {
      setDraftSteps(r.data.draft.planned_chain);
    } else {
      const msg = r.ok ? "草稿为空" : r.error;
      setFlow((f) => [...f, { id: `de${Date.now()}`, from: "system", text: `草稿生成失败：${msg}`, ts: now(), tone: "error" }]);
    }
  }

  async function submitDraft() {
    if (!draftSteps?.length || busy || !requirement.trim()) return;
    setBusy(true);
    const envelope = draftEnvelope(requirement.trim(), draftSteps, newTaskId());
    const task_id = String(envelope.task_id);
    setFlow((f) => [...f, { id: task_id, from: "ziyan", text: `确认草稿（${draftSteps.length} 步）`, ts: now() }]);
    const r = await api<{ task?: { task_id?: string } }>("/api/tasks/create", {
      method: "POST",
      body: JSON.stringify(envelope),
    });
    setBusy(false);
    if (r.ok) {
      setFlow((f) => [
        ...f,
        { id: `r${Date.now()}`, from: "system", text: `工单 ${r.data?.task?.task_id || task_id} 已按草稿创建并派发`, ts: now(), tone: "ok" },
      ]);
      setDraftSteps(null);
      setRequirement("");
    } else {
      setFlow((f) => [...f, { id: `r${Date.now()}`, from: "system", text: `创建失败：${r.error}`, ts: now(), tone: "error" }]);
    }
  }

  async function submit() {
    if (!selected || busy) return;
    const missing = missingRequired(selected.inputs || [], formValues);
    if (missing.length) {
      setFlow((f) => [
        ...f,
        { id: `v${Date.now()}`, from: "system", text: `缺少必填项：${missing.join("、")}`, ts: now(), tone: "error" },
      ]);
      return;
    }
    setBusy(true);
    const envelope = singleStepEnvelope(selected, intentText, formValues, newTaskId());
    const task_id = String(envelope.task_id);
    setFlow((f) => [...f, { id: task_id, from: "ziyan", text: intentText, ts: now() }]);
    const r = await api<{ task?: { task_id?: string; status?: string; chain?: unknown[] } }>("/api/tasks/create", {
      method: "POST",
      body: JSON.stringify(envelope),
    });
    setBusy(false);
    if (r.ok) {
      setFlow((f) => [
        ...f,
        {
          id: `r${Date.now()}`,
          from: "system",
          text: `工单 ${r.data?.task?.task_id || task_id} 已创建并派发（${selected.name_zh}）`,
          ts: now(),
          tone: "ok",
        },
      ]);
      setSelected(null);
      setFormValues({});
    } else {
      setFlow((f) => [
        ...f,
        { id: `r${Date.now()}`, from: "system", text: `创建失败：${r.error}`, ts: now(), tone: "error" },
      ]);
    }
  }

  if (!state.open) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-[90] flex w-full max-w-xl flex-col border-l border-rail bg-hull/95 shadow-2xl backdrop-blur">
      <header className="flex items-center justify-between border-b border-rail px-4 py-3">
        <div>
          <p className="hud-label">Command</p>
          {editingName ? (
            <div className="mt-0.5 flex items-center gap-1">
              <input
                autoFocus
                className="w-32 rounded border border-mint/60 bg-hull px-1.5 py-0.5 font-display text-base text-frost focus:outline-none"
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void saveName()}
              />
              <button type="button" className="text-xs text-mint" onClick={() => void saveName()}>
                保存
              </button>
              <button type="button" className="text-xs text-mute" onClick={() => setEditingName(false)}>
                取消
              </button>
            </div>
          ) : (
            <h3 className="mt-1 flex items-center gap-1.5 font-display text-base text-frost">
              指挥席位 · {identity?.display_name || "…"}
              {identity && (
                <button
                  type="button"
                  className="text-xs text-mute hover:text-mint"
                  title="改显示名（身份 ID 不变）"
                  onClick={() => {
                    setNameDraft(identity.display_name);
                    setEditingName(true);
                  }}
                >
                  ✎
                </button>
              )}
            </h3>
          )}
        </div>
        <button type="button" className="rounded px-2 py-1 text-mute hover:text-frost" onClick={() => state.setOpen(false)}>
          ✕
        </button>
      </header>

      <div ref={flowRef} className="flex-1 space-y-2 overflow-y-auto px-4 py-3" data-testid="cmd-flow">
        {flow.length === 0 && (
          <p className="soft-panel-sub text-xs text-mute">
            选择职位起草工单；执行中卡住或需要你的节点会出现在这里（二期接入被唤起通知）。
          </p>
        )}
        {flow.map((m) => (
          <div
            key={m.id}
            className={`max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed ${
              m.from === "ziyan"
                ? "ml-auto bg-rail text-frost"
                : m.tone === "error"
                  ? "bg-flare/10 text-flare"
                  : m.tone === "ok"
                    ? "bg-mint/10 text-mint"
                    : "bg-rail/40 text-mute"
            }`}
          >
            <div>{m.text}</div>
            {m.actions && m.actions.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {m.actions.map((a) => (
                  <button
                    key={a.action}
                    type="button"
                    className="rounded border border-mint/50 px-2 py-0.5 text-[11px] text-mint hover:bg-mint/15"
                    onClick={() => void runAction(a)}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="border-t border-rail px-4 py-3">
        <PositionPicker
          positions={positions}
          selected={selected}
          onSelect={(p) => {
            setSelected(p);
            setFormValues(defaults(p.inputs || []));
            setDraftSteps(null);
          }}
        />
        {selected && (
          <div className="mt-3 space-y-2">
            <InputSchemaForm fields={selected.inputs || []} values={formValues} onChange={setFormValues} />
            <button
              type="button"
              className="hud-btn w-full text-xs disabled:opacity-40"
              disabled={busy}
              onClick={() => void submit()}
            >
              {busy ? "派发中…" : `发令 · ${selected.name_zh}`}
            </button>
          </div>
        )}
        {!selected && (
          <div className="mt-3 space-y-2">
            <textarea
              rows={3}
              className="w-full rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost placeholder:text-mute/60 focus:border-mint/60 focus:outline-none"
              placeholder="或者写下自由需求，由 LLM 生成职位草稿（如：调研 Redis 缓存方案并出设计稿，最后验收）"
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
            />
            <button
              type="button"
              className="hud-btn w-full text-xs disabled:opacity-40"
              disabled={busy || !requirement.trim()}
              onClick={() => void generateDraft()}
            >
              {busy ? "生成中…" : "生成草稿"}
            </button>
            {draftSteps && (
              <>
                <DraftPreview steps={draftSteps} positions={positions} onChange={setDraftSteps} />
                <button
                  type="button"
                  className="hud-btn w-full text-xs disabled:opacity-40"
                  disabled={busy || !draftSteps.length}
                  onClick={() => void submitDraft()}
                >
                  {busy ? "派发中…" : `按草稿发令（${draftSteps.length} 步）`}
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function now() {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

export function CommandWindowButton({ state }: { state: CommandWindowState }): ReactNode {
  // 未读徽标：无论窗口开关都轮询（子言被唤起要能找到人——D1）
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const r = await api<{ unread?: number }>("/api/command/inbox");
      if (alive && r.ok && r.data) setUnread(r.data.unread || 0);
    };
    void tick();
    const timer = window.setInterval(tick, 30000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);
  return (
    <button
      type="button"
      className="fixed bottom-16 right-3 z-[85] rounded-full border border-rail bg-hull/90 px-4 py-2 font-mono text-xs text-frost shadow hover:bg-rail/60"
      title="指挥席位 · 发令"
      onClick={() => state.setOpen(!state.open)}
    >
      ⚡ 发令
      {unread > 0 && (
        <span className="ml-1.5 rounded-full bg-flare px-1.5 py-0.5 text-[10px] font-bold text-frost">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </button>
  );
}
