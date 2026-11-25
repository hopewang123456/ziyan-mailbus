import { useState } from "react";
import { Link } from "react-router-dom";
import { ConsolePageHeader, ConsoleSection, ConsoleTag } from "../../components/console/ConsoleKit";
import { Dialog } from "../../components/console/ConsoleDialog";
import { ConsolePageState } from "../../components/console/ConsolePageState";
import { can } from "../../lib/permissions";
import { useWorkflows } from "../../lib/workflow/hooks";
import { createWorkflow, deleteWorkflow, cloneVersion, publishVersion } from "../../lib/workflow/api";

/**
 * 工作流列表页：卡片 + 版本 + 发布 + 新建对话框。
 * 编辑器由 /console/workflows/{id}/v/{version} 路由懒加载。
 */
export function ConsoleWorkflowsPage({ can: canPerm }: { can: (capability: string) => boolean }) {
  void can;
  const { items, loading, error, refresh } = useWorkflows();
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const canCreate = canPerm("workflow_create");
  const canModify = canPerm("workflow_modify");
  const canPublish = canPerm("workflow_publish");

  async function onCreate() {
    const name = createName.trim();
    if (!name || busy) return;
    setBusy(true);
    setErr("");
    setMsg("");
    const result = await createWorkflow({ name });
    setBusy(false);
    if (!result.ok) { setErr(result.error); return; }
    setCreateName("");
    setCreateOpen(false);
    setMsg(`已创建工作流「${name}」`);
    refresh();
  }

  async function onDelete(id: string, name: string) {
    if (!window.confirm(`删除工作流「${name}」？有活跃 run 返回 409。`)) return;
    const result = await deleteWorkflow(id);
    if (!result.ok) { setErr(result.error); return; }
    setMsg(`已删除「${name}」`);
    refresh();
  }

  async function onClone(id: string, version: number) {
    const result = await cloneVersion(id, version);
    if (!result.ok) { setErr(result.error); return; }
    setMsg(`已派生新版本 v${result.data.version}`);
    refresh();
  }

  async function onPublish(id: string, version: number) {
    setBusy(true);
    setErr("");
    const result = await publishVersion(id, version);
    setBusy(false);
    if (!result.ok) {
      if (result.status === 409) setErr("版本冲突或校验未通过；请先校验再发布。");
      else setErr(result.error);
      return;
    }
    setMsg(`已发布 v${version}；运行中任务仍锁定原版本`);
    refresh();
  }

  if (loading && items.length === 0) {
    return (
      <>
        <ConsolePageHeader title="工作流" description="定义、版本、发布；编辑器懒加载" />
        <ConsolePageState kind="loading" title="加载中" description="拉取工作流列表…" />
      </>
    );
  }

  return (
    <>
      <ConsolePageHeader
        title="工作流"
        description="不可变版本 + revision CAS 保存；发布后新任务使用"
      />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      <ConsoleSection
        title={`工作流（${items.length}）`}
        actions={
          <button
            type="button"
            className="hud-btn text-xs disabled:opacity-40"
            disabled={!canCreate}
            onClick={() => { setCreateOpen(true); setCreateName(""); }}
          >
            新建工作流
          </button>
        }
      >
        {error && items.length === 0 ? (
          <ConsolePageState kind="error" title="加载失败" description={error} />
        ) : items.length === 0 ? (
          <ConsolePageState kind="empty" title="暂无工作流" description="点击右上角「新建工作流」开始定义。" />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((w) => (
              <article key={w.id} className="rounded-lg border border-rail bg-hull/40 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="truncate font-display text-sm text-frost">{w.name}</h3>
                    <p className="font-mono text-[10px] text-mute">{w.id}</p>
                  </div>
                  <ConsoleTag tone={w.publishedVersion ? "ok" : "default"}>
                    {w.publishedVersion ? `已发布 v${w.publishedVersion}` : "未发布"}
                  </ConsoleTag>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-mute">
                  <span>最新 v{w.latestVersion}</span>
                  {w.createdAt && <span>· 创建 {formatTime(w.createdAt)}</span>}
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {canModify && (
                    <Link
                      to={`/console/workflows/${w.id}/v/${w.latestVersion}`}
                      className="rounded border border-rail px-2 py-1 text-[11px] text-frost hover:bg-rail/30"
                    >
                      编辑 v{w.latestVersion}
                    </Link>
                  )}
                  {canCreate && (
                    <button
                      type="button"
                      className="rounded border border-rail px-2 py-1 text-[11px] text-mute hover:text-frost"
                      onClick={() => void onClone(w.id, w.latestVersion)}
                    >
                      派生 v{w.latestVersion}
                    </button>
                  )}
                  {canPublish && w.publishedVersion !== w.latestVersion && (
                    <button
                      type="button"
                      className="rounded border border-mint/50 px-2 py-1 text-[11px] text-mint hover:bg-mint/10"
                      disabled={busy}
                      onClick={() => void onPublish(w.id, w.latestVersion)}
                    >
                      发布 v{w.latestVersion}
                    </button>
                  )}
                  {canModify && (
                    <button
                      type="button"
                      className="rounded border border-flare/40 px-2 py-1 text-[11px] text-flare hover:bg-flare/10"
                      onClick={() => void onDelete(w.id, w.name)}
                    >
                      删除
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </ConsoleSection>

      <Dialog
        open={createOpen}
        title="新建工作流"
        description="首次创建即有 v1 草稿；编辑器中可添加节点、连线并保存"
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <button type="button" className="rounded border border-rail px-3 py-1.5 text-xs text-mute" onClick={() => setCreateOpen(false)}>
              取消
            </button>
            <button type="button" className="hud-btn text-xs disabled:opacity-40" disabled={busy || !createName.trim()} onClick={() => void onCreate()}>
              {busy ? "创建中…" : "创建"}
            </button>
          </>
        }
      >
        <label className="block text-[11px] text-mute">
          名称
          <input
            className="mt-1 block w-full rounded border border-rail bg-hull px-3 py-2 text-xs text-frost"
            placeholder="例如：端到端澄清 → 实现 → 验收"
            value={createName}
            autoFocus
            onChange={(e) => setCreateName(e.target.value)}
          />
        </label>
      </Dialog>
    </>
  );
}

function formatTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}
