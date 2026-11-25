import { type FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";

/** 员工入伙申请页面（/join）。 */
export function ConsoleStaffApplyPage() {
  const [params] = useSearchParams();
  const inviteCode = (params.get("invite") ?? "").trim().toUpperCase();
  const [displayName, setDisplayName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");
  const [employee, setEmployee] = useState<{ employee_id: string; status: string } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErr("");
    if (!displayName.trim()) {
      setErr("请输入显示名称");
      return;
    }
    setSubmitting(true);
    const result = await api<{ employee: { employee_id: string; status: string } }>(
      "/api/identity/staff",
      {
        method: "POST",
        body: JSON.stringify({
          display_name: displayName.trim(),
          account_type: "human",
          ...(inviteCode ? { invite_code: inviteCode } : {}),
        }),
      },
    );
    setSubmitting(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setEmployee(result.data.employee);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-abyss px-6 py-10 text-frost">
      <div className="w-full max-w-md rounded-lg border border-rail bg-hull/60 p-6">
        <h1 className="font-display text-xl">员工入伙申请</h1>
        <p className="mt-2 text-xs leading-relaxed text-mute">
          提交后等待管理员审核并激活；员工 Token 由管理员在激活后一次性交付。
        </p>
        {inviteCode ? (
          <p className="mt-3 rounded border border-mint/40 bg-mint/5 px-3 py-2 text-xs text-mint">
            已携带邀请码 <span className="font-mono">{inviteCode}</span>
            ，提交后将按邀请授予的团队/能力进入审核。
          </p>
        ) : null}
        {employee ? (
          <div className="mt-6 rounded border border-mint/40 bg-mint/5 p-4 text-xs">
            <p className="text-mint">申请已提交，请等待管理员审核。</p>
            <p className="mt-3 text-mute">申请编号</p>
            <p className="mt-1 break-all font-mono text-frost">{employee.employee_id}</p>
          </div>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={(event) => void submit(event)}>
            <label className="block text-xs text-mute">
              显示名称
              <input
                className="mt-1 block w-full rounded border border-rail bg-hull px-3 py-2 text-sm text-frost"
                value={displayName}
                maxLength={64}
                autoFocus
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
            {err && <p className="text-xs text-flare">{err}</p>}
            <button type="submit" className="hud-btn w-full text-xs" disabled={submitting}>
              {submitting ? "提交中…" : "提交申请"}
            </button>
          </form>
        )}
        <div className="mt-6 flex gap-4 text-xs text-mute">
          <a href="/console" className="hover:text-frost">管理员登录</a>
          <a href="/console" className="hover:text-frost">返回管理中心</a>
        </div>
      </div>
    </main>
  );
}
