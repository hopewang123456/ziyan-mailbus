import { useEffect, useState } from "react";
import { ErrorAlert } from "../components/ErrorAlert";
import { api } from "../lib/api";

// ── Types ────────────────────────────────────────────────────────────
type DoctorItem = {
  level: "ok" | "warn" | "fail";
  category: string;
  message: string;
  detail?: string;
};
type DoctorResp = {
  ok?: boolean;
  issues?: number;
  warnings?: number;
  items?: DoctorItem[];
};
type ClinicTool = {
  id: string;
  name?: string;
  description?: string;
  category?: string;
  readonly?: boolean;
};
type RunResult = {
  ok?: boolean;
  stdout?: string;
  stderr?: string;
  error?: string;
  tool_id?: string;
  tool_name?: string;
  returncode?: number;
  elapsed_seconds?: number;
};
type CheckEntry = { ok: boolean; detail: string; fix_hint?: string };
type AgentEntry = {
  agent: string;
  display: string;
  type: string;
  pass: boolean;
  checks: Record<string, CheckEntry>;
};
type AgentTestSummary = {
  agentmemory?: { ok: boolean; url?: string; status?: number; fix_hint?: string };
  agents?: AgentEntry[];
  summary?: { total: number; passed: number };
};
type StatusResp = {
  version?: string;
  status?: string;
  agents?: number;
  unread_messages?: number;
  total_messages?: number;
};
type TaskRow = { task_id?: string; id?: string; status?: string; summary?: string };
type TasksResp = { tasks?: TaskRow[] };
type StatsResp = {
  task_statuses?: Record<string, number>;
};

const LEVEL_STYLE: Record<string, string> = {
  fail: "text-flare",
  warn: "text-amber-signal",
  ok: "text-mint",
};
type ClinicTab = "agent" | "bus" | "tools";

// ── 修复建议卡片 ──────────────────────────────────────────────────────
function FixHintCard({ hint }: { hint: string }) {
  if (!hint) return null;
  return (
    <div className="mt-1.5 rounded border border-cyan-signal/30 bg-cyan-signal/5 px-2 py-1.5 text-[11px] text-cyan-signal">
      <span className="font-bold">💡 修复建议：</span> {hint}
    </div>
  );
}

// ── Agent 诊断 Tab ───────────────────────────────────────────────────
function AgentTab() {
  const [test, setTest] = useState<AgentTestSummary | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // 进入 tab 自动跑一次
  useEffect(() => {
    if (!test && !busy) {
      void runTests();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runTests() {
    setBusy(true);
    setErr("");
    const r = await api<AgentTestSummary>("/api/test-agents");
    setBusy(false);
    if (r.ok) setTest(r.data);
    else setErr(r.error);
  }

  const agents = test?.agents || [];
  const failed = agents.filter((a) => !a.pass);

  // 统计各类型失败
  const failByCheck: Record<string, number> = {};
  for (const a of failed) {
    for (const [name, info] of Object.entries(a.checks || {})) {
      if (!info.ok) failByCheck[name] = (failByCheck[name] || 0) + 1;
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm text-mute">
            配置完整性 · 容器状态 · 浏览器可达性 · 身份文件 · AgentMemory。
            {test?.summary && !busy && (
              <span className={test.summary.passed === test.summary.total ? "text-mint" : "text-flare"}>
                {" "}— {test.summary.passed}/{test.summary.total} 通过
              </span>
            )}
          </p>
          {Object.keys(failByCheck).length > 0 && (
            <p className="text-xs text-flare mt-0.5">
              {Object.entries(failByCheck)
                .map(([k, v]) => `${k}×${v}`)
                .join(" · ")}
            </p>
          )}
        </div>
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void runTests()}>
          {busy ? "检测中…" : "重新检测"}
        </button>
      </div>
      <ErrorAlert message={err} />

      {/* AgentMemory 条 */}
      {test?.agentmemory != null && (
        <div className={`rounded-sm border px-3 py-2 text-xs ${test.agentmemory.ok ? "border-mint/30 bg-mint/5" : "border-flare/30 bg-flare/5"}`}>
          <span className="text-mute">AgentMemory: </span>
          <span className={test.agentmemory.ok ? "text-mint" : "text-flare"}>
            {test.agentmemory.ok ? "可连通" : "不可达"}
          </span>
          <span className="text-mute ml-2">{test.agentmemory.url} (HTTP {test.agentmemory.status})</span>
          {!test.agentmemory.ok && test.agentmemory.fix_hint && (
            <div className="mt-1 text-[11px] text-cyan-signal">💡 {test.agentmemory.fix_hint}</div>
          )}
        </div>
      )}

      {/* 全部通过 */}
      {test && failed.length === 0 && (
        <div className="rounded-sm border border-mint/20 bg-mint/5 p-4 text-center">
          <p className="text-mint font-display text-lg">全部检测通过 ✓</p>
          <p className="text-xs text-mute mt-1">13 个 Agent 配置完整，容器运行正常，浏览器可达，身份就绪</p>
        </div>
      )}

      {/* Agent 卡片列表 */}
      {agents.length > 0 && (
        <div className="space-y-2">
          {agents.map((a) => {
            const chk = a.checks || {};
            const failures = Object.entries(chk).filter(([, info]) => !info.ok);
            if (a.pass) {
              // 通过的 agent 紧凑显示
              return (
                <div key={a.agent} className="rounded-sm border border-mint/20 bg-mint/3 p-2 text-xs flex items-center gap-3">
                  <span className="text-mint shrink-0">✓</span>
                  <span className="font-mono text-frost w-14">{a.display}</span>
                  <span className="text-mute w-16">{a.type}</span>
                  <span className="text-mint ml-auto">PASS</span>
                </div>
              );
            }
            // 失败的 agent 完整展示
            return (
              <div key={a.agent} className="rounded-sm border border-flare/20 bg-flare/3 p-3 text-xs">
                <div className="flex flex-wrap items-baseline gap-2 mb-2">
                  <span className="font-mono text-frost text-sm">{a.display}</span>
                  <span className="text-mute">{a.type}</span>
                  <span className="ml-auto text-flare font-bold">FAIL</span>
                </div>
                {failures.map(([name, info]) => (
                  <div key={name} className="ml-2 pl-2 border-l-2 border-flare/30 mb-1.5">
                    <div className="flex items-start gap-2">
                      <span className="text-flare shrink-0 mt-px">✗</span>
                      <div>
                        <span className="text-mute">{name}: </span>
                        <span className="text-amber-signal">{info.detail}</span>
                        <FixHintCard hint={info.fix_hint || ""} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}

      {!test && busy && (
        <p className="text-sm text-mute text-center py-8 animate-pulse">正在检测全部 Agent…</p>
      )}
    </div>
  );
}

// ── 总线修复 Tab ────────────────────────────────────────────────────
function BusTab() {
  const [doctor, setDoctor] = useState<DoctorResp | null>(null);
  const [status, setStatus] = useState<StatusResp | null>(null);
  const [stats, setStats] = useState<StatsResp | null>(null);
  const [tasks, setTasks] = useState<TasksResp | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void Promise.all([
      api<StatusResp>("/api/status"),
      api<StatsResp>("/api/stats"),
      api<TasksResp>("/api/tasks?limit=50"),
    ]).then(([sR, stR, tR]) => {
      if (sR.ok) setStatus(sR.data);
      if (stR.ok) setStats(stR.data);
      if (tR.ok) setTasks({ tasks: Array.isArray(tR.data?.tasks) ? tR.data.tasks : [] });
    });
  }, []);

  async function runDoctor() {
    setBusy(true);
    setErr("");
    const r = await api<DoctorResp>("/api/doctor");
    setBusy(false);
    if (r.ok) setDoctor(r.data);
    else setErr(r.error);
  }
  async function loadAll() {
    setBusy(true);
    setErr("");
    const [dR, stR, tR] = await Promise.all([
      api<DoctorResp>("/api/doctor"),
      api<StatsResp>("/api/stats"),
      api<TasksResp>("/api/tasks?limit=50"),
    ]);
    setBusy(false);
    if (dR.ok) setDoctor(dR.data);
    if (stR.ok) setStats(stR.data);
    if (tR.ok) setTasks({ tasks: Array.isArray(tR.data?.tasks) ? tR.data.tasks : [] });
    const errors = [dR, stR, tR].filter((r) => !r.ok).map((r) => r.error).filter(Boolean);
    if (errors.length) setErr(errors.join("; "));
  }

  const ts = stats?.task_statuses || {};
  const totalTasks = Object.values(ts).reduce((a, b) => a + b, 0);
  const brokenTasks = (ts.failed || 0) + (ts.timeout || 0) + (ts.cancelled || 0);
  const taskList = tasks?.tasks || [];
  const nonOkTasks = taskList.filter((t) => t.status && !["success", "completed", "done"].includes(t.status));

  // Doctor 分组
  const doctorFailWarn = (doctor?.items || []).filter((i) => i.level !== "ok");

  return (
    <div className="space-y-4">
      <p className="text-sm text-mute">
        总线健康 + 任务链诊断。一键检查 mailbus 自身状态、scheduler、Docker 挂载、框架完整性，并检测任务链断开/丢失。
      </p>

      {/* 状态条 */}
      {status && (
        <div className="rounded-sm border border-rail bg-hull/50 px-3 py-2 text-xs flex flex-wrap gap-x-4 gap-y-1">
          <span>
            <span className="text-mute">总线: </span>
            <span className={status.status === "ok" ? "text-mint" : "text-amber-signal"}>
              {status.status || status.version || "…"}
            </span>
          </span>
          <span className="text-mute">agents {status.agents ?? "—"}</span>
          <span className="text-mute">消息 {status.total_messages ?? "—"} / 未读 {status.unread_messages ?? "—"}</span>
          {stats && (
            <span>
              <span className="text-mute">任务: </span>
              <span className={brokenTasks > 0 ? "text-flare" : "text-mint"}>{totalTasks} 个</span>
              {brokenTasks > 0 && <span className="text-flare"> · {brokenTasks} 异常</span>}
            </span>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void loadAll()}>
          {busy ? "诊断中…" : "一键诊断"}
        </button>
      </div>
      <ErrorAlert message={err} />

      {/* ── 任务链诊断 ── */}
      {stats && (
        <div className="rounded-sm border border-rail bg-hull/50 p-4">
          <p className="hud-label mb-3">任务链诊断</p>
          <div className="grid grid-cols-5 gap-2 text-center text-xs">
            {[
              ["运行中", ts.running || 0, "text-cyan-signal"],
              ["等待中", ts.pending || 0, "text-amber-signal"],
              ["成功", ts.success || 0, "text-mint"],
              ["失败", ts.failed || 0, "text-flare"],
              ["超时/取消", (ts.timeout || 0) + (ts.cancelled || 0), "text-flare"],
            ].map(([label, count, color]) => (
              <div key={label as string} className="border border-rail/30 rounded py-2">
                <p className={`text-lg font-display ${color}`}>{count as number}</p>
                <p className="text-[10px] text-mute mt-0.5">{label as string}</p>
              </div>
            ))}
          </div>

          {/* 异常任务列表 */}
          {nonOkTasks.length > 0 && (
            <div className="mt-3 pt-3 border-t border-rail/30">
              <p className="text-xs text-flare font-bold mb-2">
                ⚠ {nonOkTasks.length} 个任务存在异常状态：
              </p>
              <ul className="space-y-1 max-h-48 overflow-auto">
                {nonOkTasks.map((t) => {
                  const id = String(t.task_id || t.id || "");
                  return (
                    <li key={id} className="text-xs border-l-2 border-flare/30 pl-2 py-1">
                      <span className="font-mono text-frost">{id}</span>
                      <span className={`ml-2 ${t.status === "failed" ? "text-flare" : "text-amber-signal"}`}>
                        {t.status}
                      </span>
                      {t.summary && <span className="text-mute ml-2 truncate">{t.summary}</span>}
                    </li>
                  );
                })}
              </ul>
              <p className="text-[10px] text-mute mt-2">
                前往「任务」面板可查看详细 FSM 状态、审批、重试操作
              </p>
            </div>
          )}
          {nonOkTasks.length === 0 && totalTasks > 0 && (
            <p className="text-xs text-mint mt-2">所有任务状态正常 — 无丢失或异常</p>
          )}
          {totalTasks === 0 && (
            <p className="text-xs text-mute mt-2">暂无任务记录</p>
          )}
        </div>
      )}

      {/* Doctor 问题 */}
      {doctor && (
        <div className="rounded-sm border border-rail bg-hull/50 p-4">
          <div className="flex flex-wrap gap-3 text-xs mb-3">
            <span className={doctor.ok ? "text-mint" : "text-flare"}>{doctor.ok ? "OK" : "ISSUES"}</span>
            <span className="text-flare">issues {doctor.issues ?? 0}</span>
            <span className="text-amber-signal">warnings {doctor.warnings ?? 0}</span>
          </div>
          {doctorFailWarn.length === 0 ? (
            <p className="text-xs text-mint">总线健康 — 所有检查通过</p>
          ) : (
            <ul className="space-y-1 max-h-60 overflow-auto">
              {doctorFailWarn.map((item, idx) => (
                <li key={idx} className={`border-l-2 pl-2 py-1 text-xs ${LEVEL_STYLE[item.level]} border-current`}>
                  <span className="text-mute">[{item.category}]</span> {item.message}
                  {item.detail && <p className="font-mono text-mute text-[10px] truncate">{item.detail}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!doctor && (
        <p className="text-xs text-mute text-center py-4">点击「一键诊断」检查总线健康与任务链</p>
      )}
    </div>
  );
}

// ── 其它工具 Tab ─────────────────────────────────────────────────────
function ToolsTab() {
  const [tools, setTools] = useState<ClinicTool[]>([]);
  const [runResults, setRunResults] = useState<Record<string, RunResult>>({});
  const [running, setRunning] = useState("");
  const [err, setErr] = useState("");
  const [llmStatus, setLlmStatus] = useState<unknown>(null);
  const [llmHealth, setLlmHealth] = useState<unknown>(null);

  useEffect(() => {
    void (async () => {
      const r = await api<{ tools?: ClinicTool[] }>("/api/clinic/tools");
      if (r.ok) setTools(Array.isArray(r.data.tools) ? r.data.tools : []);
    })();
  }, []);

  async function runTool(toolId: string) {
    setRunning(toolId);
    const r = await api<RunResult>("/api/clinic/run", {
      method: "POST",
      body: JSON.stringify({ tool_id: toolId, preset_index: 0 }),
    });
    setRunning("");
    if (r.ok || r.data) setRunResults((p) => ({ ...p, [toolId]: r.data as RunResult }));
    if (!r.ok) setErr(r.error);
  }

  async function loadInternalLlm() {
    const [s, h] = await Promise.all([
      api("/api/internal-llm/status"),
      api("/api/internal-llm/health"),
    ]);
    if (s.ok) setLlmStatus(s.data);
    else setErr(s.error);
    if (h.ok) setLlmHealth(h.data);
  }

  const agentTools = tools.filter((t) => (t.category || "").includes("Agent"));
  const busTools = tools.filter((t) =>
    (t.category || "").includes("mailbus") || (t.category || "").includes("Docker") || (t.category || "").includes("迁移")
  );
  const authTools = tools.filter((t) => (t.category || "").includes("鉴权"));
  const otherTools = tools.filter((t) => {
    const c = t.category || "";
    return !c.includes("Agent") && !c.includes("mailbus") && !c.includes("Docker") && !c.includes("迁移") && !c.includes("鉴权");
  });

  function renderToolGroup(title: string, desc: string, list: ClinicTool[]) {
    if (list.length === 0) return null;
    return (
      <div key={title} className="space-y-2">
        <div className="mb-1">
          <p className="hud-label">{title}</p>
          <p className="text-[10px] text-mute">{desc}</p>
        </div>
        {list.map((t) => {
          const result = runResults[t.id];
          return (
            <div key={t.id} className="rounded-sm border border-rail/50 p-2 text-xs">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-frost">{t.name || t.id}</p>
                  {t.description && <p className="text-mute mt-0.5">{t.description}</p>}
                </div>
                <button
                  type="button"
                  className="hud-btn shrink-0"
                  disabled={running === t.id}
                  onClick={() => void runTool(t.id)}
                >
                  {running === t.id ? "…" : "Run"}
                </button>
              </div>
              {result && (
                <div className={`mt-2 p-2 rounded ${result.ok ? "bg-mint/5 border border-mint/20" : "bg-flare/5 border border-flare/20"}`}>
                  <p className={`${result.ok ? "text-mint" : "text-flare"}`}>
                    {result.ok ? "ok" : (result.error || "failed")}
                    {result.elapsed_seconds != null && (
                      <span className="text-mute ml-2">{result.elapsed_seconds}s</span>
                    )}
                  </p>
                  {result.stdout && (
                    <pre className="mt-1 max-h-40 overflow-auto text-[10px] text-mute">{result.stdout.slice(-2000)}</pre>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-mute">
        深度诊断工具，按分类分组。当 Agent 诊断/总线修复都无法定位时，用这些工具针对性地校验配置、鉴权、Compose 挂载。
      </p>
      <ErrorAlert message={err} />

      {renderToolGroup("Agent 配置", "检查 config.json 中 agent 的 CLI 类型、profile、launch 模板一致性", agentTools)}
      {renderToolGroup("Agent 鉴权", "修复 Cline 鉴权、探测 Hermes 对话连通性", authTools)}
      {renderToolGroup("mailbus 总线 & Compose", "全量诊断、Compose 挂载校验、同步 Override", busTools)}
      {renderToolGroup("其它", "源码完整性、n8n 工作流发布", otherTools)}

      <div className="rounded-sm border border-rail bg-hull/50 p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="hud-label">Internal LLM</p>
          <button type="button" className="hud-btn text-xs" onClick={() => void loadInternalLlm()}>
            Load
          </button>
        </div>
        <div className="mt-2 grid gap-3 md:grid-cols-2">
          <pre className="max-h-32 overflow-auto text-xs text-mute">
            status: {llmStatus == null ? "—" : JSON.stringify(llmStatus, null, 2)}
          </pre>
          <pre className="max-h-32 overflow-auto text-xs text-mute">
            health: {llmHealth == null ? "—" : JSON.stringify(llmHealth, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}

// ── 主页面 ───────────────────────────────────────────────────────────
export function ClinicPage() {
  const [tab, setTab] = useState<ClinicTab>("agent");

  const TABS: { id: ClinicTab; label: string; desc: string }[] = [
    { id: "agent", label: "Agent 诊断", desc: "自动检测 · 修复建议" },
    { id: "bus", label: "总线修复", desc: "Doctor · 任务链" },
    { id: "tools", label: "其它工具", desc: "深度配置校验" },
  ];

  return (
    <div className="space-y-4">
      <header>
        <p className="hud-label">Medbay</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide">诊所</h2>
        <p className="mt-1 text-sm text-mute">
          一键诊断 + 修复建议 — 代替手动排查常见异常：
          <span className="text-amber-signal"> 浏览器/终端进不去</span> ·
          <span className="text-cyan-signal"> 任务丢失/断链</span> ·
          <span className="text-flare"> 配置缺失</span>
        </p>
      </header>

      {/* 子 Tab 栏 */}
      <div className="flex gap-1 rounded-sm border border-rail bg-hull/30 p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`flex-1 rounded px-3 py-2 text-sm transition ${
              tab === t.id ? "bg-rail text-frost" : "text-mute hover:bg-rail/40 hover:text-frost"
            }`}
            onClick={() => setTab(t.id)}
          >
            <span className="block font-display tracking-wide">{t.label}</span>
            <span className="block text-[10px] opacity-60">{t.desc}</span>
          </button>
        ))}
      </div>

      {tab === "agent" && <AgentTab />}
      {tab === "bus" && <BusTab />}
      {tab === "tools" && <ToolsTab />}
    </div>
  );
}
