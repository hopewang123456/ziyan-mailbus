/** LLM 草稿预览（D4 草稿确认制）：职位节点卡片，可删/调序/换职位，确认后按 explicit 提交 */
import type { Position } from "./PositionPicker";

export type DraftStep = { role_type: number; reason: string };

export function DraftPreview({
  steps,
  positions,
  onChange,
}: {
  steps: DraftStep[];
  positions: Position[];
  onChange(steps: DraftStep[]): void;
}) {
  const move = (i: number, delta: number) => {
    const j = i + delta;
    if (j < 0 || j >= steps.length) return;
    const next = [...steps];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };

  return (
    <div className="space-y-1.5" data-testid="draft-preview">
      <p className="soft-panel-sub text-[11px] text-mute">
        LLM 草稿（确认制）：可删除、调序或更换职位后发令。
      </p>
      {steps.map((s, i) => (
        <div key={i} className="flex items-center gap-2 rounded border border-rail bg-rail/20 px-2 py-1.5">
          <span className="font-mono text-[10px] text-mute">{i + 1}</span>
          <select
            className="rounded border border-rail bg-hull px-1.5 py-0.5 text-xs text-frost focus:border-mint/60 focus:outline-none"
            value={s.role_type}
            onChange={(e) => {
              const rt = Number(e.target.value);
              onChange(steps.map((x, k) => (k === i ? { ...x, role_type: rt } : x)));
            }}
          >
            {positions.map((p) => (
              <option key={p.role_type} value={p.role_type}>
                {p.name_zh}
              </option>
            ))}
          </select>
          <input
            type="text"
            className="min-w-0 flex-1 rounded border border-rail bg-hull px-1.5 py-0.5 text-xs text-mute focus:border-mint/60 focus:outline-none"
            value={s.reason}
            placeholder="步骤理由"
            onChange={(e) => onChange(steps.map((x, k) => (k === i ? { ...x, reason: e.target.value } : x)))}
          />
          <button type="button" className="text-mute hover:text-frost" title="上移" onClick={() => move(i, -1)}>
            ↑
          </button>
          <button type="button" className="text-mute hover:text-frost" title="下移" onClick={() => move(i, 1)}>
            ↓
          </button>
          <button
            type="button"
            className="text-mute hover:text-flare"
            title="删除步骤"
            onClick={() => onChange(steps.filter((_, k) => k !== i))}
          >
            ✕
          </button>
        </div>
      ))}
      {steps.length === 0 && <p className="text-[11px] text-flare">草稿已清空——至少保留一个步骤。</p>}
    </div>
  );
}
