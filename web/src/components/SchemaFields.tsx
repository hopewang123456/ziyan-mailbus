import { useState, type ReactNode } from "react";

/**
 * 轻量 schema 驱动表单：把 config.json 各 section 的字段渲染成表单控件。
 * 值全部保存在一个 Record<string, unknown> 状态树里，保存时仍组装成 JSON patch。
 */

export type FieldSpec =
  | {
      kind: "group";
      key?: string;
      label?: string;
      children: FieldSpec[];
      help?: string;
    }
  | {
      kind: "string" | "text" | "number" | "boolean" | "enum" | "stringArray" | "json";
      key: string;
      label: string;
      options?: string[] | Record<string, string>;
      placeholder?: string;
      secret?: boolean;
      help?: string;
      min?: number;
      max?: number;
    };

type Value = Record<string, unknown>;

export type SchemaFieldsProps = {
  specs: FieldSpec[];
  value: Value;
  onChange: (key: string, value: unknown) => void;
  disabled?: boolean;
};

export function asRecord(v: unknown): Value {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Value) : {};
}

function StringArrayInput({
  value,
  onChange,
  options,
  placeholder,
  disabled,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  options?: string[];
  placeholder?: string;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const list = Array.isArray(value) ? value : [];
  function add() {
    const items = draft
      .split(/[,，\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!items.length) return;
    onChange(Array.from(new Set([...list, ...items])));
    setDraft("");
  }
  const listId = options && options.length ? `dl-${options[0]}` : undefined;
  return (
    <div>
      {list.length > 0 && (
        <div className="flex flex-wrap gap-1 pb-1">
          {list.map((m) => (
            <span
              key={m}
              className="flex items-center gap-1 rounded border border-mint/20 bg-mint/5 px-2 py-0.5 font-mono text-[11px] text-mint"
            >
              {m}
              <button
                type="button"
                disabled={disabled}
                className="text-mute hover:text-flare"
                onClick={() => onChange(list.filter((x) => x !== m))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-1">
        <input
          className="hud-input flex-1 font-mono text-xs"
          value={draft}
          list={listId}
          disabled={disabled}
          placeholder={placeholder || "回车/逗号添加"}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add();
            }
          }}
          onBlur={add}
        />
        <button type="button" className="hud-btn !px-2" disabled={disabled} onClick={add}>
          +
        </button>
      </div>
      {listId && (
        <datalist id={listId}>
          {options!.map((o) => (
            <option key={o} value={o} />
          ))}
        </datalist>
      )}
    </div>
  );
}

function JsonField({
  raw,
  onChange,
  disabled,
  label,
}: {
  raw: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
  label: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  function openEdit() {
    setText(raw == null ? "" : JSON.stringify(raw, null, 2));
    setErr("");
    setOpen(true);
  }
  function commit() {
    try {
      const parsed = text.trim() ? JSON.parse(text) : undefined;
      onChange(parsed);
      setErr("");
      setOpen(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "JSON 无效");
    }
  }
  return (
    <div className="space-y-1">
      {label}
      {!open ? (
        <div className="flex items-center gap-2">
          <span className="truncate font-mono text-[11px] text-mute">
            {raw == null ? "（空）" : JSON.stringify(raw).slice(0, 80)}
          </span>
          <button type="button" className="hud-btn !px-2" disabled={disabled} onClick={openEdit}>
            编辑 JSON
          </button>
        </div>
      ) : (
        <div className="space-y-1">
          <textarea
            className="hud-input w-full font-mono text-xs"
            rows={5}
            value={text}
            disabled={disabled}
            spellCheck={false}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex gap-2">
            <button type="button" className="hud-btn" disabled={disabled} onClick={commit}>
              应用
            </button>
            <button type="button" className="hud-btn-amber" onClick={() => setOpen(false)}>
              取消
            </button>
          </div>
        </div>
      )}
      {err && <p className="text-xs text-flare">{err}</p>}
    </div>
  );
}

function LeafField({
  spec,
  value,
  onChange,
  disabled,
}: {
  spec: Exclude<FieldSpec, { kind: "group" }>;
  value: Value;
  onChange: (key: string, v: unknown) => void;
  disabled?: boolean;
}) {
  const raw = value[spec.key];
  const id = `f-${spec.key}`;
  const label = (
    <label className="hud-label block" htmlFor={spec.kind === "boolean" ? undefined : id}>
      {spec.label}
      {spec.secret && <span className="ml-1 text-amber">(secret)</span>}
    </label>
  );

  switch (spec.kind) {
    case "boolean": {
      const on = raw === true;
      return (
        <div className="flex items-center gap-2">
          <input
            id={id}
            type="checkbox"
            checked={on}
            disabled={disabled}
            onChange={(e) => onChange(spec.key, e.target.checked)}
          />
          {label}
        </div>
      );
    }
    case "number":
      return (
        <label className="block">
          {label}
          <input
            id={id}
            className="hud-input mt-1 w-32 font-mono text-xs"
            type="number"
            min={spec.min}
            max={spec.max}
            value={raw == null ? "" : String(raw)}
            disabled={disabled}
            onChange={(e) => onChange(spec.key, e.target.value === "" ? undefined : Number(e.target.value))}
          />
        </label>
      );
    case "enum": {
      const options = spec.options || [];
      const arr = Array.isArray(options) ? options : Object.keys(options);
      return (
        <label className="block">
          {label}
          <select
            id={id}
            className="hud-input mt-1 w-full font-mono text-xs"
            value={raw == null ? "" : String(raw)}
            disabled={disabled}
            onChange={(e) => onChange(spec.key, e.target.value)}
          >
            <option value="">—</option>
            {arr.map((o) => (
              <option key={o} value={o}>
                {Array.isArray(options) ? o : options[o]}
              </option>
            ))}
          </select>
        </label>
      );
    }
    case "stringArray":
      return (
        <div>
          {label}
          <div className="mt-1">
            <StringArrayInput
              value={Array.isArray(raw) ? (raw as string[]) : []}
              onChange={(v) => onChange(spec.key, v)}
              options={Array.isArray(spec.options) ? spec.options : undefined}
              placeholder={spec.placeholder}
              disabled={disabled}
            />
          </div>
        </div>
      );
    case "json":
      return <JsonField raw={raw} onChange={(v) => onChange(spec.key, v)} disabled={disabled} label={label} />;
    case "text":
      return (
        <label className="block">
          {label}
          <textarea
            className="hud-input mt-1 w-full font-mono text-xs"
            rows={3}
            value={raw == null ? "" : String(raw)}
            disabled={disabled}
            placeholder={spec.placeholder}
            onChange={(e) => onChange(spec.key, e.target.value)}
          />
        </label>
      );
    default: {
      return (
        <label className="block">
          {label}
          <input
            id={id}
            className="hud-input mt-1 w-full font-mono text-xs"
            type={spec.secret ? "password" : "text"}
            value={raw == null ? "" : String(raw)}
            disabled={disabled}
            placeholder={spec.placeholder}
            autoComplete="off"
            onChange={(e) => onChange(spec.key, e.target.value)}
          />
        </label>
      );
    }
  }
}

function GroupBlock({
  spec,
  value,
  onChange,
  disabled,
}: {
  spec: Extract<FieldSpec, { kind: "group" }>;
  value: Value;
  onChange: (key: string, v: unknown) => void;
  disabled?: boolean;
}) {
  const bound = spec.key ? asRecord(value[spec.key]) : value;
  const childOnChange = (k: string, v: unknown) => {
    if (spec.key) onChange(spec.key, { ...bound, [k]: v });
    else onChange(k, v);
  };
  const body = <SchemaFields specs={spec.children} value={bound} onChange={childOnChange} disabled={disabled} />;
  if (!spec.key && !spec.label) return body;
  return (
    <fieldset className="space-y-2 rounded border border-rail/60 bg-abyss/20 p-2">
      {spec.label && <legend className="hud-label px-1">{spec.label}</legend>}
      {body}
      {spec.help && <p className="text-[11px] text-mute">{spec.help}</p>}
    </fieldset>
  );
}

export function SchemaFields({ specs, value, onChange, disabled }: SchemaFieldsProps) {
  return (
    <div className="space-y-2">
      {specs.map((spec) =>
        spec.kind === "group" ? (
          <GroupBlock key={spec.key || "grp"} spec={spec} value={value} onChange={onChange} disabled={disabled} />
        ) : (
          <LeafField key={spec.key} spec={spec} value={value} onChange={onChange} disabled={disabled} />
        ),
      )}
    </div>
  );
}
