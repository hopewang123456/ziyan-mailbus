import { useCallback, useState } from "react";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";
import { ConsoleDrawer } from "../../components/console/ConsoleDrawer";
import { useAudits, useAudit } from "../../lib/audit/hooks";

/** 审计日志：列表 + 筛选（actor/action/resource/时间范围）+ 详情抽屉。 */

function timeText(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function ConsoleAuditPage() {
  const [actor, setActor] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null);
  const [resource, setResource] = useState<string | null>(null);
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);

  const {
    items: audits,
    total,
    loading,
    error,
    refresh,
  } = useAudits({
    actor,
    action,
    resource,
    from,
    to,
    limit: 200,
    offset: 0,
  });

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data: detail } = useAudit(selectedId);

  const openDetail = useCallback((row: any) => {
    setSelectedId(row.audit_id);
  }, []);

  const closeDetail = useCallback(() => {
    setSelectedId(null);
  }, []);

  return (
    <>
      <ConsolePageHeader
        title="审计日志"
        description="全量操作审计，按 actor/action/resource/时间范围筛选"
        actions={
          <button type="button" className="hud-btn text-xs" onClick={() => void refresh()}>
            刷新
          </button>
        }
      />
      {error && <p className="mb-3 text-xs text-flare">{error}</p>}

      {/* === 筛选区 === */}
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-mute">
          操作人
          <input
            className="mt-1 block w-32 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            placeholder="actor_id"
            value={actor ?? ""}
            onChange={(e) => setActor(e.target.value || null)}
          />
        </label>
        <label className="text-[11px] text-mute">
          动作
          <input
            className="mt-1 block w-28 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            placeholder="action"
            value={action ?? ""}
            onChange={(e) => setAction(e.target.value || null)}
          />
        </label>
        <label className="text-[11px] text-mute">
          资源
          <input
            className="mt-1 block w-36 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            placeholder="resource"
            value={resource ?? ""}
            onChange={(e) => setResource(e.target.value || null)}
          />
        </label>
        <label className="text-[11px] text-mute">
          起始
          <input
            type="datetime-local"
            className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={from ?? ""}
            onChange={(e) => setFrom(e.target.value ? new Date(e.target.value).toISOString() : null)}
          />
        </label>
        <label className="text-[11px] text-mute">
          结束
          <input
            type="datetime-local"
            className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={to ?? ""}
            onChange={(e) => setTo(e.target.value ? new Date(e.target.value).toISOString() : null)}
          />
        </label>
        <button type="button" className="hud-btn text-xs" onClick={() => void refresh()}>
          查询
        </button>
      </div>

      {/* === 审计列表 === */}
      <ConsoleSection title={`审计日志（${audits.length} / ${total}）`}>
        <ConsoleTable
          rows={audits}
          rowKey={(row: any) => row.audit_id}
          loading={loading}
          empty="暂无审计记录"
          onRowClick={(row: any) => openDetail(row)}
          selectedKey={selectedId !== null ? String(selectedId) : undefined}
          columns={[
            {
              key: "id",
              header: "#",
              render: (row: any) => <span className="font-mono text-[11px]">{String(row.audit_id)}</span>,
            },
            {
              key: "actor",
              header: "操作人",
              render: (row: any) => <span className="font-mono text-[11px]">{row.actor_id || "system"}</span>,
            },
            {
              key: "action",
              header: "动作",
              render: (row: any) => <ConsoleTag>{row.action}</ConsoleTag>,
            },
            {
              key: "resource",
              header: "资源",
              render: (row: any) => (
                <span className="font-mono text-[11px] text-mute">{row.resource || "—"}</span>
              ),
            },
            {
              key: "detail",
              header: "明细",
              render: (row: any) => (
                <span className="font-mono text-[11px] text-mute">
                  {row.detail ? JSON.stringify(row.detail).slice(0, 80) : "—"}
                </span>
              ),
            },
            {
              key: "time",
              header: "时间",
              render: (row: any) => <span className="text-[11px] text-mute">{timeText(row.created_at)}</span>,
            },
          ]}
        />
      </ConsoleSection>

      {/* === 详情抽屉 === */}
      {selectedId !== null && (
        <ConsoleDrawer
          open
          onClose={closeDetail}
          title={`审计详情 · #${selectedId}`}
        >
          {detail && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <Field label="审计 ID" value={String(detail.audit_id)} />
                <Field label="操作人" value={detail.actor_id || "system"} />
                <Field label="动作" value={detail.action} />
                <Field label="资源" value={detail.resource || "—"} />
                <Field label="时间" value={timeText(detail.created_at)} />
              </div>
              {detail.detail && (
                <div>
                  <p className="mb-1 text-[11px] text-mute">详情</p>
                  <pre className="rounded border border-rail bg-hull px-2 py-1 text-xs text-frost font-mono whitespace-pre-wrap break-all">
                    {JSON.stringify(detail.detail, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </ConsoleDrawer>
      )}
    </>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-mute">{label}</p>
      <p className="font-mono text-frost break-all">{value}</p>
    </div>
  );
}
