/** 职位选择器（D3：节点=职位而非具体角色；候选池含空闲态，未 pin 则派发器空闲优先） */
export type Candidate = {
  agent_id: string;
  name: string;
  framework: string;
  available: boolean;
  busy: boolean;
  active_tasks: number;
};

export type InputField = {
  name: string;
  label?: { zh?: string; en?: string };
  type: "string" | "text" | "enum" | "number" | "boolean";
  required?: boolean;
  default?: string | number | boolean;
  options?: string[];
  placeholder?: { zh?: string };
};

export type Position = {
  role_type: number;
  key: string;
  name_zh: string;
  name_en: string;
  default_sla_minutes?: number | null;
  inputs: InputField[];
  candidates: Candidate[];
};

export function PositionPicker({
  positions,
  selected,
  onSelect,
}: {
  positions: Position[];
  selected: Position | null;
  onSelect(p: Position): void;
}) {
  if (!positions.length) {
    return <p className="soft-panel-sub text-xs text-mute">职位目录为空（检查 /api/positions 与 role-types.json）</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5" data-testid="position-picker">
      {positions.map((p) => {
        const idle = p.candidates.filter((c) => c.available && !c.busy).length;
        const active = selected?.role_type === p.role_type;
        return (
          <button
            key={p.role_type}
            type="button"
            title={`${p.name_zh} · 候选 ${p.candidates.length}（空闲 ${idle}）`}
            className={`rounded-full border px-2.5 py-1 text-xs transition ${
              active
                ? "border-mint bg-mint/15 text-mint"
                : "border-rail text-mute hover:border-mint/50 hover:text-frost"
            }`}
            onClick={() => onSelect(p)}
          >
            {p.name_zh}
            {p.candidates.length > 0 && (
              <span className={`ml-1 font-mono text-[10px] ${idle ? "text-mint" : "text-flare"}`}>{idle || "忙"}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
