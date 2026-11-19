import { useEffect, useState } from "react";
import { api, setToken } from "../../lib/api";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTag,
} from "../../components/console/ConsoleKit";

/** 首次部署向导：超管 → 模型配置 → 首团队；后两步可跳过。 */

type Step = { step: string; done: boolean; skippable: boolean };
type Status = { steps: Step[]; completed: boolean };

const STEP_LABEL: Record<string, string> = {
  super_admin: "超级管理员",
  model_config: "模型配置",
  first_team: "首个团队",
};

export function ConsoleSetupPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [adminName, setAdminName] = useState("");
  const [provider, setProvider] = useState("deepseek");
  const [model, setModel] = useState("deepseek-v4");
  const [apiBase, setApiBase] = useState("");
  const [teamName, setTeamName] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = async () => {
    const result = await api<Status>("/api/identity/bootstrap");
    if (result.ok) {
      setStatus(result.data);
      setErr("");
    } else {
      setErr(result.error);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  async function run(path: string, body: unknown, okMsg: string) {
    setErr("");
    setMsg("");
    const result = await api(path, { method: "POST", body: JSON.stringify(body) });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(okMsg);
    await load();
  }

  async function createSuperAdmin() {
    setErr("");
    setMsg("");
    if (!adminName.trim()) {
      setErr("请输入超级管理员显示名称");
      return;
    }
    const result = await api<{ token: string }>("/api/identity/bootstrap/super-admin", {
      method: "POST",
      body: JSON.stringify({ display_name: adminName.trim() }),
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setToken(result.data.token);
    setMsg("已创建超级管理员并自动登录");
    await load();
  }

  const done = (step: string) => status?.steps.find((item) => item.step === step)?.done;

  return (
    <>
      <ConsolePageHeader
        title="设置向导"
        description="首次部署三步：创建超级管理员 → 配置模型 → 建首个团队。除超管外均可跳过"
      />

      {status && (
        <p className="mb-4 text-xs text-mute">
          整体状态：
          <ConsoleTag tone={status.completed ? "ok" : "warn"}>
            {status.completed ? "已完成" : "进行中"}
          </ConsoleTag>
        </p>
      )}

      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      <ConsoleSection
        title={`1. ${STEP_LABEL.super_admin}`}
        actions={
          <ConsoleTag tone={done("super_admin") ? "ok" : "warn"}>
            {done("super_admin") ? "已完成" : "待完成"}
          </ConsoleTag>
        }
      >
        {done("super_admin") ? (
          <p className="text-xs text-mute">超级管理员已创建，不可重复执行。</p>
        ) : (
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-[11px] text-mute">
              显示名称
              <input
                className="mt-1 block w-48 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                value={adminName}
                onChange={(e) => setAdminName(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="hud-btn text-xs"
              onClick={() => void createSuperAdmin()}
            >
              创建
            </button>
          </div>
        )}
      </ConsoleSection>

      <ConsoleSection
        title={`2. ${STEP_LABEL.model_config}`}
        actions={
          <ConsoleTag tone={done("model_config") ? "ok" : "warn"}>
            {done("model_config") ? "已完成" : "待完成"}
          </ConsoleTag>
        }
      >
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-mute">
            Provider
            <input
              className="mt-1 block w-32 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-mute">
            模型
            <input
              className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-mute">
            API Base
            <input
              className="mt-1 block w-64 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder="可选"
            />
          </label>
          <button
            type="button"
            className="hud-btn text-xs"
            onClick={() =>
              void run(
                "/api/identity/bootstrap/model-config",
                { provider, model, api_base: apiBase.trim() || null },
                "模型配置已保存",
              )
            }
          >
            保存
          </button>
          <button
            type="button"
            className="rounded border border-rail px-2.5 py-1 text-xs text-mute hover:text-frost"
            onClick={() =>
              void run("/api/identity/bootstrap/model_config/skip", {}, "已跳过模型配置")
            }
          >
            跳过
          </button>
        </div>
      </ConsoleSection>

      <ConsoleSection
        title={`3. ${STEP_LABEL.first_team}`}
        actions={
          <ConsoleTag tone={done("first_team") ? "ok" : "warn"}>
            {done("first_team") ? "已完成" : "待完成"}
          </ConsoleTag>
        }
      >
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-mute">
            团队名称
            <input
              className="mt-1 block w-48 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="hud-btn text-xs"
            onClick={() =>
              void run(
                "/api/identity/bootstrap/team",
                { name: teamName.trim() },
                "已创建首个团队",
              )
            }
          >
            创建
          </button>
          <button
            type="button"
            className="rounded border border-rail px-2.5 py-1 text-xs text-mute hover:text-frost"
            onClick={() =>
              void run("/api/identity/bootstrap/first_team/skip", {}, "已跳过首个团队")
            }
          >
            跳过
          </button>
        </div>
      </ConsoleSection>
    </>
  );
}
