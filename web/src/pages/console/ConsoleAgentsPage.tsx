import { useState } from "react";
import { ConfirmDialog } from "../../components/console/ConsoleDialog";
import { ConsoleDrawer } from "../../components/console/ConsoleDrawer";
import { ConsolePageState } from "../../components/console/ConsolePageState";
import { ConsoleTabs, useTabParam } from "../../components/console/ConsoleTabs";
import { buildA2aOnboardingPrompt } from "../../lib/collab/agentOnboarding";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";
import {
  approveEndpoint as apiApproveEndpoint,
  createAgentInvite as apiCreateAgentInvite,
  deleteAgent as apiDeleteAgent,
  rejectEndpoint as apiRejectEndpoint,
  revokeAgentInvite as apiRevokeAgentInvite,
  revokeToken as apiRevokeToken,
  rotateToken as apiRotateToken,
  unbindAgent as apiUnbindAgent,
} from "../../lib/agent/api";
import { useAgents, useAgentInvites } from "../../lib/agent/hooks";
import {
  CHANNEL_TYPE_LABELS,
  ENDPOINT_REVIEW_LABELS,
} from "../../lib/agent/view";
import type { AgentRow, AgentInviteRow } from "../../lib/agent/view";
import { PERMISSION_GROUPS, PERMISSION_LABELS } from "../../lib/permissions";
import { DATA_SCOPE_LABELS } from "../../lib/permissions";

const TABS = ["shells", "invites"] as const;
const TAB_LABELS: Record<(typeof TABS)[number], string> = {
  shells: "外壳",
  invites: "邀请码",
};

export interface ConsoleAgentsPageProps {
  can: (capability: string) => boolean;
}

// ──────────────────────────────────────────────────────────────
// 主入口
// ──────────────────────────────────────────────────────────────

export function ConsoleAgentsPage({ can }: ConsoleAgentsPageProps) {
  const [tab, setTab] = useTabParam(TABS, "shells");

  return (
    <>
      <ConsolePageHeader
        title="Agent"
        description="外壳台账与邀请码"
      />
      <ConsoleTabs
        tabs={TABS.map((key) => ({ key, label: TAB_LABELS[key] }))}
        value={tab}
        onChange={setTab}
      />
      {tab === "shells" && <ShellsTab can={can} />}
      {tab === "invites" && <InvitesTab can={can} />}
    </>
  );
}

// ──────────────────────────────────────────────────────────────
// 外壳 Tab
// ──────────────────────────────────────────────────────────────

function ShellsTab({ can }: { can: (c: string) => boolean }) {
  const { items, loading, error, refresh } = useAgents({ limit: 200 });

  const consoleAdmin = can("console_admin");
  const orgManage = can("org_manage");
  const agentDeregister = can("agent_deregister");
  const canManageRow = orgManage || agentDeregister;

  // 操作状态
  const [rotatedToken, setRotatedToken] = useState<{ agent: AgentRow; token: string } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<AgentRow | null>(null);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const handleApprove = async (agent: AgentRow) => {
    const res = await apiApproveEndpoint(agent.id);
    if (res.ok) refresh();
  };
  const handleReject = async (agent: AgentRow) => {
    const res = await apiRejectEndpoint(agent.id);
    if (res.ok) refresh();
  };
  const handleRotate = async (agent: AgentRow) => {
    const res = await apiRotateToken(agent.id);
    if (res.ok && res.data) {
      setRotatedToken({ agent, token: res.data.token });
    }
  };
  const handleRevokeToken = async (agent: AgentRow) => {
    const res = await apiRevokeToken(agent.id);
    if (res.ok) refresh();
  };
  const handleUnbind = async (agent: AgentRow) => {
    const res = await apiUnbindAgent(agent.id);
    if (res.ok) refresh();
  };

  const handleDelete = async (agent: AgentRow) => {
    setDeleteErr(null);
    const res = await apiDeleteAgent(agent.id);
    if (res.ok) {
      setDeleteConfirm(null);
      refresh();
    } else if (!res.ok) {
      if (res.status === 409) {
        setDeleteErr("Agent 有活跃任务");
      } else {
        setDeleteErr(res.error || "删除失败");
      }
    }
  };

  if (loading && items.length === 0) return <ConsolePageState kind="loading" />;
  if (error) return <ConsolePageState kind="error" description={error} />;

  return (
    <>
      <ConsoleSection
        title={`外壳（${items.length}）`}
        actions={
          <button
            type="button"
            className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
            onClick={refresh}
          >
            刷新
          </button>
        }
      >
        <ConsoleTable<AgentRow>
          rows={items}
          rowKey={(row) => row.id}
          loading={loading}
          empty="暂无 Agent 外壳"
          columns={[
            {
              key: "id",
              header: "ID",
              render: (row) => <span className="font-mono">{row.id.slice(0, 8)}</span>,
            },
            { key: "name", header: "名称", render: (row) => row.name },
            { key: "agentType", header: "类型", render: (row) => <ConsoleTag>{row.agentType}</ConsoleTag> },
            {
              key: "channel",
              header: "通道",
              render: (row) => (
                <ConsoleTag>{CHANNEL_TYPE_LABELS[row.channelType] ?? row.channelType}</ConsoleTag>
              ),
            },
            { key: "framework", header: "框架", render: (row) => row.framework || "—" },
            { key: "model", header: "模型", render: (row) => row.model || "—" },
            {
              key: "endpoint",
              header: "端点",
              render: (row) => (
                <span className="font-mono text-[11px]">{row.pendingEndpoint ?? row.endpoint ?? "—"}</span>
              ),
            },
            {
              key: "review",
              header: "端点审批",
              render: (row) => {
                const label = ENDPOINT_REVIEW_LABELS[row.endpointReviewStatus] ?? row.endpointReviewStatus;
                const tone: "ok" | "warn" | "danger" | "default" =
                  row.endpointReviewStatus === "approved" ? "ok" :
                  row.endpointReviewStatus === "pending" ? "warn" :
                  row.endpointReviewStatus === "rejected" ? "danger" : "default";
                return <ConsoleTag tone={tone}>{label}</ConsoleTag>;
              },
            },
            {
              key: "enabled",
              header: "状态",
              render: (row) =>
                row.enabled ? (
                  <ConsoleTag tone="ok">启用</ConsoleTag>
                ) : (
                  <ConsoleTag tone="danger">停用</ConsoleTag>
                ),
            },
            {
              key: "online",
              header: "在线",
              render: (row) =>
                row.online ? (
                  <ConsoleTag tone="ok">在线</ConsoleTag>
                ) : (
                  <ConsoleTag tone="default">离线</ConsoleTag>
                ),
            },
            {
              key: "actions",
              header: "操作",
              className: "min-w-[240px]",
              render: (row) => (
                <span className="flex flex-wrap items-center gap-1">
                  {row.endpointReviewStatus === "pending" && consoleAdmin && (
                    <>
                      <button
                        type="button"
                        className="rounded border border-mint/50 px-2 py-0.5 text-[11px] text-mint hover:bg-mint/10"
                        onClick={() => void handleApprove(row)}
                      >
                        批准
                      </button>
                      <button
                        type="button"
                        className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10"
                        onClick={() => void handleReject(row)}
                      >
                        拒绝
                      </button>
                    </>
                  )}
                  {consoleAdmin && (
                    <>
                      <button
                        type="button"
                        className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost"
                        onClick={() => void handleRotate(row)}
                      >
                        轮转
                      </button>
                      <button
                        type="button"
                        className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10"
                        onClick={() => void handleRevokeToken(row)}
                      >
                        吊销
                      </button>
                    </>
                  )}
                  {canManageRow && (
                    <>
                      <button
                        type="button"
                        className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost"
                        onClick={() => void handleUnbind(row)}
                      >
                        解绑
                      </button>
                      <button
                        type="button"
                        className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10"
                        onClick={() => {
                          setDeleteErr(null);
                          setDeleteConfirm(row);
                        }}
                      >
                        注销
                      </button>
                    </>
                  )}
                </span>
              ),
            },
          ]}
        />
      </ConsoleSection>

      {/* Token 轮转结果抽屉：token 明文仅组件状态内持有 */}
      {rotatedToken && (
        <ConsoleDrawer
          open
          width={560}
          onClose={() => setRotatedToken(null)}
          title={`Token 轮转成功 — ${rotatedToken.agent.name}`}
          description="明文仅本次显示，复制后关闭。"
        >
          <RotateTokenView token={rotatedToken.token} />
        </ConsoleDrawer>
      )}

      {/* 删除确认 */}
      <ConfirmDialog
        open={deleteConfirm !== null}
        title={deleteConfirm ? `注销 Agent「${deleteConfirm.name}」？` : ""}
        description={
          deleteErr ?? "软注销：状态移除，解绑员工关联。"
        }
        danger
        confirmLabel="注销"
        onCancel={() => {
          setDeleteConfirm(null);
          setDeleteErr(null);
        }}
        onConfirm={() => {
          if (deleteConfirm) void handleDelete(deleteConfirm);
        }}
      />
    </>
  );
}

function RotateTokenView({ token }: { token: string }) {
  return (
    <div className="space-y-3">
      <div className="rounded border border-mint/40 bg-mint/5 px-3 py-2 font-mono text-sm text-mint break-all">
        {token}
      </div>
      <p className="text-[11px] text-mute">
        该 Token 只在本组件生命周期内可见，页面刷新或关闭抽屉后不再保留。
      </p>
      <button
        type="button"
        className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
        onClick={() => {
          navigator.clipboard?.writeText(token).catch(() => {});
        }}
      >
        复制到剪贴板
      </button>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// 邀请码 Tab
// ──────────────────────────────────────────────────────────────

function InvitesTab({ can }: { can: (c: string) => boolean }) {
  const { items, loading, error, refresh } = useAgentInvites({ limit: 200 });
  const consoleAdmin = can("console_admin");
  const orgManage = can("org_manage");
  const canCreate = consoleAdmin || orgManage;

  const [createOpen, setCreateOpen] = useState(false);

  if (loading && items.length === 0) return <ConsolePageState kind="loading" />;
  if (error) return <ConsolePageState kind="error" description={error} />;

  return (
    <>
      <ConsoleSection
        title={`邀请码（${items.length}）`}
        actions={
          <span className="flex items-center gap-2">
            {canCreate && (
              <button type="button" className="hud-btn text-xs" onClick={() => setCreateOpen(true)}>
                创建
              </button>
            )}
            <button
              type="button"
              className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
              onClick={refresh}
            >
              刷新
            </button>
          </span>
        }
      >
        <ConsoleTable<AgentInviteRow>
          rows={items}
          rowKey={(row) => row.id}
          loading={loading}
          empty="暂无 Agent 邀请码"
          columns={[
            {
              key: "id",
              header: "ID",
              render: (row) => <span className="font-mono">{row.id.slice(0, 8)}</span>,
            },
            { key: "agentType", header: "类型", render: (row) => <ConsoleTag>{row.agentType}</ConsoleTag> },
            {
              key: "channel",
              header: "通道",
              render: (row) => (
                <ConsoleTag>{CHANNEL_TYPE_LABELS[row.channelType] ?? row.channelType}</ConsoleTag>
              ),
            },
            {
              key: "scope",
              header: "数据范围",
              render: (row) => (
                <ConsoleTag>{DATA_SCOPE_LABELS[row.dataScope as keyof typeof DATA_SCOPE_LABELS] ?? row.dataScope}</ConsoleTag>
              ),
            },
            {
              key: "employee",
              header: "员工",
              render: (row) => row.employeeName ?? "—",
            },
            {
              key: "expires",
              header: "过期时间",
              render: (row) =>
                row.expiresAt ? (
                  <span className="font-mono text-[11px]">{row.expiresAt}</span>
                ) : (
                  <ConsoleTag tone="ok">长期</ConsoleTag>
                ),
            },
            {
              key: "status",
              header: "状态",
              render: (row) => (
                <InviteStatusTag invite={row} />
              ),
            },
            {
              key: "actions",
              header: "操作",
              render: (row) => {
                const usable = !row.revokedAt && !row.usedAt;
                return (
                  <span className="flex items-center gap-1">
                    {canCreate && usable && (
                      <RevokeInviteButton
                        inviteId={row.id}
                        onDone={refresh}
                      />
                    )}
                  </span>
                );
              },
            },
          ]}
        />
      </ConsoleSection>

      {createOpen && (
        <CreateAgentInviteDialog
          onClose={() => setCreateOpen(false)}
          onDone={() => {
            setCreateOpen(false);
            refresh();
          }}
        />
      )}
    </>
  );
}

function InviteStatusTag({ invite }: { invite: AgentInviteRow }) {
  if (invite.revokedAt) return <ConsoleTag tone="danger">已撤销</ConsoleTag>;
  if (invite.usedAt) return <ConsoleTag tone="ok">已使用</ConsoleTag>;
  if (!invite.expiresAt) return <ConsoleTag tone="ok">长期有效</ConsoleTag>;
  const expired = new Date(invite.expiresAt).getTime() < Date.now();
  if (expired) return <ConsoleTag tone="warn">已过期</ConsoleTag>;
  return <ConsoleTag tone="default">未使用</ConsoleTag>;
}

function RevokeInviteButton({
  inviteId,
  onDone,
}: {
  inviteId: string;
  onDone: () => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const confirm = async () => {
    setBusy(true);
    setErr(null);
    const res = await apiRevokeAgentInvite(inviteId);
    setBusy(false);
    if (res.ok) {
      setConfirmOpen(false);
      onDone();
    } else if (!res.ok) {
      setErr(res.error || "撤销失败");
    }
  };

  return (
    <>
      <button
        type="button"
        className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10"
        onClick={() => setConfirmOpen(true)}
      >
        撤销
      </button>
      <ConfirmDialog
        open={confirmOpen}
        title="撤销邀请码？"
        description={err ?? "撤销后 Agent 无法通过该码注册。"}
        danger
        busy={busy}
        onConfirm={() => void confirm()}
        onCancel={() => {
          setConfirmOpen(false);
          setErr(null);
        }}
      />
    </>
  );
}

// ── 创建 Agent 邀请码对话框 ────────────────────────────────────

function CreateAgentInviteDialog({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  const [agentType, setAgentType] = useState<string>("external");
  const [channelType, setChannelType] = useState<"a2a" | "file_bus" | "pull_only">("a2a");
  const [dataScope, setDataScope] = useState<"self" | "team" | "global">("self");
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [expiresIn, setExpiresIn] = useState<number | null>(24);
  const [employeeName, setEmployeeName] = useState<string>("");
  const [positionId] = useState<string>("");

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<{
    inviteCode: string;
    agentType: string;
    channelType: string;
  } | null>(null);

  const submit = async () => {
    setErr(null);
    setBusy(true);
    const res = await apiCreateAgentInvite({
      agent_type: agentType,
      channel_type: channelType,
      data_scope: dataScope,
      capabilities,
      permissions,
      expires_in_hours: expiresIn,
      employee_name: employeeName.trim() || null,
      position_id: positionId || null,
    });
    setBusy(false);
    if (res.ok && res.data) {
      setResult({
        inviteCode: res.data.invite_code ?? "",
        agentType: res.data.agent_type,
        channelType: res.data.channel_type,
      });
    } else if (!res.ok) {
      setErr(res.error || "创建失败");
    }
  };

  if (result) {
    return (
      <ConsoleDrawer
        open
        width={640}
        title="Agent 邀请码已创建"
        description="明文仅本次展示；关闭后不再可见。"
        onClose={onDone}
        footer={
          <div className="flex justify-end">
            <button type="button" className="hud-btn text-xs" onClick={onDone}>
              完成
            </button>
          </div>
        }
      >
        <InviteCodeShowcase
          inviteCode={result.inviteCode}
          agentType={result.agentType}
          channelType={result.channelType}
        />
      </ConsoleDrawer>
    );
  }

  return (
    <ConsoleDrawer
      open
      width={640}
      title="创建 Agent 邀请码"
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
            onClick={onClose}
          >
            取消
          </button>
          <button
            type="button"
            className="hud-btn text-xs disabled:opacity-40"
            disabled={busy}
            onClick={() => void submit()}
          >
            {busy ? "提交中…" : "创建"}
          </button>
        </div>
      }
    >
      <div className="space-y-3">
        <label className="block text-[11px] text-mute">
          Agent 类型
          <input
            className="mt-1 w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={agentType}
            onChange={(e) => setAgentType(e.target.value)}
          />
        </label>
        <label className="block text-[11px] text-mute">
          通道类型
          <select
            className="mt-1 w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={channelType}
            onChange={(e) => setChannelType(e.target.value as any)}
          >
            <option value="a2a">A2A</option>
            <option value="file_bus">文件总线</option>
            <option value="pull_only">仅拉取</option>
          </select>
        </label>
        <label className="block text-[11px] text-mute">
          数据范围
          <select
            className="mt-1 w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={dataScope}
            onChange={(e) => setDataScope(e.target.value as any)}
          >
            <option value="self">仅本人</option>
            <option value="team">本团队</option>
            <option value="global">全部</option>
          </select>
        </label>
        <CapabilityChooser values={capabilities} onChange={setCapabilities} />
        <PermissionChooser values={permissions} onChange={setPermissions} />
        <label className="block text-[11px] text-mute">
          有效期（小时）。留空表示长期有效。
          <input
            type="number"
            min={1}
            className="mt-1 w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={expiresIn ?? ""}
            placeholder="长期有效"
            onChange={(e) => {
              const v = e.target.value;
              setExpiresIn(v === "" ? null : Number(v));
            }}
          />
        </label>
        <label className="block text-[11px] text-mute">
          关联员工名称（可选）
          <input
            className="mt-1 w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={employeeName}
            onChange={(e) => setEmployeeName(e.target.value)}
          />
        </label>
        {err && <p className="text-xs text-flare">{err}</p>}
      </div>
    </ConsoleDrawer>
  );
}

function CapabilityChooser({
  values,
  onChange,
}: {
  values: string[];
  onChange: (next: string[]) => void;
}) {
  const [input, setInput] = useState("");
  const add = () => {
    const v = input.trim();
    if (!v || values.includes(v)) return;
    onChange([...values, v]);
    setInput("");
  };
  return (
    <div>
      <p className="mb-1 text-[11px] text-mute">capabilities（可手动添加）</p>
      <div className="mb-1 flex flex-wrap gap-1">
        {values.length === 0 && <span className="text-[11px] text-mute">（无）</span>}
        {values.map((c) => (
          <span key={c} className="inline-flex items-center gap-1 rounded border border-rail px-1.5 py-0.5 text-[11px]">
            {c}
            <button
              type="button"
              className="text-mute hover:text-flare"
              onClick={() => onChange(values.filter((x) => x !== c))}
            >
              ✕
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          className="min-w-0 flex-1 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
          placeholder="回车添加"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <button
          type="button"
          className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
          onClick={add}
        >
          添加
        </button>
      </div>
    </div>
  );
}

function PermissionChooser({
  values,
  onChange,
}: {
  values: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div>
      <p className="mb-1 text-[11px] text-mute">permissions</p>
      <div className="max-h-48 space-y-1 overflow-y-auto rounded border border-rail bg-hull/40 p-2">
        {PERMISSION_GROUPS.map((group) => (
          <div key={group.key}>
            <p className="text-[11px] text-mute">{group.label}</p>
            <div className="grid grid-cols-2 gap-1">
              {group.permissions.map((p) => {
                const checked = values.includes(p.key);
                return (
                  <label key={p.key} className="flex items-center gap-1 text-xs" title={p.description}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) onChange([...values, p.key]);
                        else onChange(values.filter((x) => x !== p.key));
                      }}
                    />
                    {PERMISSION_LABELS[p.key]}
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 邀请码展示：HTTP curl / MCP 配置 / system_prompt ──────────

function InviteCodeShowcase({
  inviteCode,
  agentType,
  channelType,
}: {
  inviteCode: string;
  agentType: string;
  channelType: string;
}) {
  const [subTab, setSubTab] = useState<"a2a" | "curl" | "mcp" | "prompt">("a2a");
  const curlCmd = `curl -X POST /api/agents/register \\\n  -H 'Content-Type: application/json' \\\n  -d '{
  "name": "my-agent",
  "agent_type": "${agentType}",
  "channel_type": "${channelType}",
  "framework": "claude",
  "endpoint": "http://127.0.0.1:8000/agent",
  "invite_code": "${inviteCode}"
}'`;
  const mcpConfig = `# MCP servers.json 示例（需自备 MCP 适配层；无适配层可改用「HTTP curl」直连）
{
  "mcpServers": {
    "mailbus-agent": {
      "command": "python",
      "args": ["-m", "mailbus.mcp"],
      "env": {
        "MAILBUS_AGENT_NAME": "my-agent",
        "MAILBUS_INVITE_CODE": "${inviteCode}"
      }
    }
  }
}

# Tools（MCP 工具面已收敛为 4 个，见 shared/contracts/mcp-tools-v0.json）
- mailbus_inbox      GET  /api/mcp/pull
- mailbus_send       POST /api/mcp/messages
- mailbus_ack        POST /api/a2a/messages (type=ack)
- mailbus_result     POST /api/a2a/messages (type=result)`;
  const prompt = `# System Prompt for Mailbus Agent Integration

You are joining the Mailbus multi-agent bus.

Your invite code (use once): ${inviteCode}

Register via:
  POST /api/agents/register

After registration, you receive a persistent Agent Token.
Use that token in Authorization: Bearer <token> for subsequent calls.

Available endpoints:
  POST /api/agents/{agent_id}/heartbeat
  POST /api/messages
  GET  /api/tasks
  POST /api/tasks/{task_id}/result`;

  const mailbusBase = typeof window !== "undefined" ? window.location.origin : "";
  const a2aPrompt = buildA2aOnboardingPrompt({ mailbusBase, inviteCode });

  const tabs = [
    { key: "a2a" as const, label: "A2A 接入模板" },
    { key: "curl" as const, label: "HTTP curl" },
    { key: "mcp" as const, label: "MCP 四工具" },
    { key: "prompt" as const, label: "快速上手" },
  ];

  const content =
    subTab === "a2a"
      ? a2aPrompt
      : subTab === "curl"
        ? curlCmd
        : subTab === "mcp"
          ? mcpConfig
          : prompt;

  return (
    <div className="space-y-3">
      <p className="text-xs text-mute">邀请码：</p>
      <div className="rounded border border-mint/40 bg-mint/5 px-3 py-2 font-mono text-sm text-mint break-all">
        {inviteCode}
      </div>
      <ConsoleTabs tabs={tabs} value={subTab} onChange={setSubTab} />
      <pre className="max-h-[28rem] overflow-auto rounded border border-rail bg-hull/60 p-3 font-mono text-[11px] leading-relaxed text-frost/90 whitespace-pre-wrap">
        {content}
      </pre>
      <button
        type="button"
        className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
        onClick={() => {
          navigator.clipboard?.writeText(content).catch(() => {});
        }}
      >
        复制当前内容
      </button>
    </div>
  );
}
