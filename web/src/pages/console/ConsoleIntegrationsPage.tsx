import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";

/** 集成与运行配置：插件增删、动作调用占位、环境变量与重载。 */

type Integration = { name: string; kind: string; description: string; actions: string[] };
type EnvEntry = { key: string; label: string; value: string; configured: boolean };
type EnvGroups = Record<string, EnvEntry[]>;

export function ConsoleIntegrationsPage({ can }: { can: (capability: string) => boolean }) {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [plugins, setPlugins] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [env, setEnv] = useState<EnvGroups>({});
  const [pluginSpec, setPluginSpec] = useState("");
  const [envDrafts, setEnvDrafts] = useState<Record<string, string>>({});
  const [invokeResult, setInvokeResult] = useState<{ name: string; data: unknown } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const canManage = can("system_config");

  const load = useCallback(async () => {
    setLoading(true);
    const [integrationsRes, envRes] = await Promise.all([
      api<{ integrations?: Integration[]; plugins?: string[]; note?: string }>(
        "/api/settings/integrations",
      ),
      api<{ groups?: EnvGroups }>("/api/settings/env"),
    ]);
    setLoading(false);
    const errors: string[] = [];
    if (integrationsRes.ok && integrationsRes.data) {
      setIntegrations(integrationsRes.data.integrations ?? []);
      setPlugins(integrationsRes.data.plugins ?? []);
      setNote(integrationsRes.data.note ?? "");
    } else if (!integrationsRes.ok) errors.push(`集成：${integrationsRes.error}`);
    if (envRes.ok && envRes.data?.groups) setEnv(envRes.data.groups);
    else if (!envRes.ok) errors.push(`运行配置：${envRes.error}`);
    setErr(errors.join("；"));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function pluginAction(action: "add_plugin" | "remove_plugin", spec: string) {
    setBusy(true);
    setErr("");
    setMsg("");
    const result = await api<{ plugins?: string[] }>("/api/settings/integrations", {
      method: "POST",
      body: JSON.stringify({ action, spec }),
    });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setPlugins(result.data.plugins ?? []);
    setMsg(action === "add_plugin" ? `已加入插件 ${spec}` : `已移除插件 ${spec}`);
    if (action === "add_plugin") setPluginSpec("");
  }

  async function invoke(integration: Integration, action: string) {
    setBusy(true);
    setErr("");
    setMsg("");
    const result = await api<Record<string, unknown>>(
      `/api/settings/integrations/${encodeURIComponent(integration.name)}/invoke`,
      { method: "POST", body: JSON.stringify({ action, params: {} }) },
    );
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setInvokeResult({ name: `${integration.name} · ${action}`, data: result.data });
    const ok = (result.data as { ok?: boolean })?.ok;
    setMsg(
      ok === true
        ? "调用已返回成功"
        : "接口已响应，但集成尚未配置（合同占位，不是前端错误）",
    );
  }

  async function saveEnv() {
    setBusy(true);
    setErr("");
    setMsg("");
    const result = await api<{ groups?: EnvGroups }>("/api/settings/env", {
      method: "POST",
      body: JSON.stringify({ vars: envDrafts }),
    });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setEnv(result.data.groups ?? {});
    setEnvDrafts({});
    setMsg("运行配置已保存");
  }

  async function reload() {
    setBusy(true);
    setErr("");
    setMsg("");
    const result = await api<{ reloaded?: boolean; plugins?: string[] }>("/api/dev/reload", {
      method: "POST",
    });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setPlugins(result.data.plugins ?? []);
    setMsg(
      result.data.reloaded
        ? "插件已重载"
        : "重载接口已响应；当前实现为占位，未实际重建插件进程",
    );
  }

  return (
    <>
      <ConsolePageHeader
        title="集成"
        description="外部服务、插件与运行配置（读写需要 system_config）"
        actions={
          <button type="button" className="hud-btn text-xs" onClick={() => void load()}>
            刷新
          </button>
        }
      />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}
      {note && <p className="mb-3 text-[11px] text-mute">{note}</p>}
      {!canManage && (
        <p className="mb-3 text-[11px] text-amber-signal">当前账号只读；修改需要 system_config。</p>
      )}

      <ConsoleSection title={`集成（${integrations.length}）`}>
        <ConsoleTable
          rows={integrations}
          rowKey={(row) => row.name}
          loading={loading}
          empty="暂无集成"
          columns={[
            { key: "name", header: "名称", render: (row) => <span className="font-mono">{row.name}</span> },
            { key: "kind", header: "类型", render: (row) => <ConsoleTag>{row.kind}</ConsoleTag> },
            { key: "desc", header: "说明", render: (row) => <span className="text-mute">{row.description}</span> },
            {
              key: "act",
              header: "动作",
              render: (row) => (
                <span className="flex flex-wrap gap-1">
                  {row.actions.length === 0 && <span className="text-mute">—</span>}
                  {row.actions.map((action) => (
                    <button
                      key={action}
                      type="button"
                      disabled={!canManage || busy}
                      className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                      onClick={() => void invoke(row, action)}
                    >
                      {action}
                    </button>
                  ))}
                </span>
              ),
            },
          ]}
        />
      </ConsoleSection>

      {invokeResult && (
        <ConsoleSection title={`调用结果 · ${invokeResult.name}`}>
          <pre className="max-h-56 overflow-auto rounded border border-rail bg-hull/60 p-3 font-mono text-[11px] text-frost/85">
            {JSON.stringify(invokeResult.data, null, 2)}
          </pre>
        </ConsoleSection>
      )}

      <ConsoleSection title={`插件（${plugins.length}）`}>
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <label className="flex-1 text-[11px] text-mute">
            插件 spec
            <input
              className="mt-1 block w-full min-w-56 rounded border border-rail bg-hull px-2 py-1.5 font-mono text-xs text-frost"
              value={pluginSpec}
              placeholder="例如 mailbus.plugins.example:plugin"
              disabled={!canManage}
              onChange={(event) => setPluginSpec(event.target.value)}
            />
          </label>
          <button
            type="button"
            className="hud-btn text-xs disabled:opacity-40"
            disabled={!canManage || busy || !pluginSpec.trim()}
            onClick={() => void pluginAction("add_plugin", pluginSpec.trim())}
          >
            添加
          </button>
          <button
            type="button"
            className="rounded border border-rail px-2.5 py-1 text-xs text-mute hover:text-frost disabled:opacity-40"
            disabled={!canManage || busy}
            onClick={() => void reload()}
          >
            重载插件
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {plugins.length === 0 && <p className="text-xs text-mute">暂无插件</p>}
          {plugins.map((plugin) => (
            <span
              key={plugin}
              className="inline-flex items-center gap-1.5 rounded border border-rail bg-hull/50 px-2 py-1 font-mono text-[11px] text-frost/85"
            >
              {plugin}
              <button
                type="button"
                disabled={!canManage || busy}
                className="text-mute hover:text-flare disabled:opacity-40"
                title="移除插件"
                onClick={() => void pluginAction("remove_plugin", plugin)}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      </ConsoleSection>

      <ConsoleSection title="运行配置">
        {Object.entries(env).length === 0 ? (
          <p className="text-xs text-mute">{loading ? "加载中…" : "暂无运行配置项"}</p>
        ) : (
          <div className="space-y-4">
            {Object.entries(env).map(([group, entries]) => (
              <div key={group}>
                <p className="mb-1.5 text-[11px] uppercase tracking-wider text-mute">{group}</p>
                <div className="space-y-1.5">
                  {entries.map((entry) => (
                    <div
                      key={entry.key}
                      className="flex flex-wrap items-center gap-2 rounded border border-rail bg-hull/40 px-3 py-2"
                    >
                      <span className="w-56 shrink-0 font-mono text-[11px] text-frost/85">
                        {entry.key}
                      </span>
                      <span className="w-32 shrink-0 truncate text-[11px] text-mute">{entry.label}</span>
                      <input
                        className="min-w-48 flex-1 rounded border border-rail bg-hull px-2 py-1 font-mono text-[11px] text-frost"
                        placeholder={entry.configured ? "已配置，留空表示不修改" : "未配置"}
                        value={envDrafts[entry.key] ?? ""}
                        disabled={!canManage}
                        onChange={(event) =>
                          setEnvDrafts((prev) => ({ ...prev, [entry.key]: event.target.value }))
                        }
                      />
                      <ConsoleTag tone={entry.configured ? "ok" : "warn"}>
                        {entry.configured ? "已配置" : "未配置"}
                      </ConsoleTag>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={!canManage || busy || Object.keys(envDrafts).length === 0}
              onClick={() => void saveEnv()}
            >
              保存运行配置
            </button>
          </div>
        )}
      </ConsoleSection>
    </>
  );
}
