/** inputs 动态表单（D3/D4：选职位后按 SoT schema 自动渲染，填完直接发） */
import type { InputField } from "./PositionPicker";

export type FormValues = Record<string, string | number | boolean>;

export function InputSchemaForm({
  fields,
  values,
  onChange,
}: {
  fields: InputField[];
  values: FormValues;
  onChange(v: FormValues): void;
}) {
  if (!fields.length) {
    return <p className="soft-panel-sub text-xs text-mute">该职位未声明表单 schema，走自由指令（LLM 草稿路径建设中）</p>;
  }
  const set = (name: string, v: string | number | boolean) => onChange({ ...values, [name]: v });

  return (
    <div className="space-y-2">
      {fields.map((f) => {
        const label = f.label?.zh || f.name;
        const common =
          "w-full rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost placeholder:text-mute/60 focus:border-mint/60 focus:outline-none";
        return (
          <label key={f.name} className="block">
            <span className="mb-1 block text-[11px] text-mute">
              {label}
              {f.required && <span className="ml-0.5 text-flare">*</span>}
            </span>
            {f.type === "text" ? (
              <textarea
                rows={3}
                className={common}
                placeholder={f.placeholder?.zh || ""}
                value={String(values[f.name] ?? "")}
                onChange={(e) => set(f.name, e.target.value)}
              />
            ) : f.type === "enum" ? (
              <select className={common} value={String(values[f.name] ?? f.default ?? "")} onChange={(e) => set(f.name, e.target.value)}>
                {(f.options || []).map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : f.type === "boolean" ? (
              <input
                type="checkbox"
                className="accent-mint"
                checked={Boolean(values[f.name] ?? f.default)}
                onChange={(e) => set(f.name, e.target.checked)}
              />
            ) : f.type === "number" ? (
              <input
                type="number"
                className={common}
                value={String(values[f.name] ?? "")}
                onChange={(e) => set(f.name, e.target.value === "" ? "" : Number(e.target.value))}
              />
            ) : (
              <input
                type="text"
                className={common}
                placeholder={f.placeholder?.zh || ""}
                value={String(values[f.name] ?? "")}
                onChange={(e) => set(f.name, e.target.value)}
              />
            )}
          </label>
        );
      })}
    </div>
  );
}
