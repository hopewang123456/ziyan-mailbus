import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { getToken } from "../lib/api";

type AuthDetail = {
  status?: number;
  path?: string;
  hadToken?: boolean;
  stale?: boolean;
  write?: boolean;
};

/**
 * 写 API 默认要 Token：无 Token 或 401 时引导去配置合页。
 */
export function AuthTokenBanner() {
  const loc = useLocation();
  const [visible, setVisible] = useState(() => !getToken());
  const [stale, setStale] = useState(false);

  useEffect(() => {
    const onNeed = (e: Event) => {
      const d = ((e as CustomEvent).detail || {}) as AuthDetail;
      setVisible(true);
      setStale(Boolean(d.stale || d.hadToken));
    };
    const onOk = () => {
      setVisible(!getToken());
      setStale(false);
    };
    window.addEventListener("mailbus:auth-required", onNeed);
    window.addEventListener("mailbus:auth-ok", onOk);
    return () => {
      window.removeEventListener("mailbus:auth-required", onNeed);
      window.removeEventListener("mailbus:auth-ok", onOk);
    };
  }, []);

  if (loc.pathname.startsWith("/legacy")) return null;
  if (!visible) return null;

  const title = stale
    ? "API Token 无效或已过期"
    : "写操作需要 API Token";
  const body = stale
    ? "本机保存的 Token 已清除。请到配置合页重新填写或轮换。"
    : "默认本机写 API 也需要 Bearer Token（不再因 loopback 免鉴权）。";

  return (
    <div className="pointer-events-auto fixed left-1/2 top-3 z-[90] w-[min(92vw,36rem)] -translate-x-1/2 rounded border border-amber-signal/50 bg-hull/95 px-3 py-2 text-sm text-frost shadow">
      <p className="font-medium text-amber-signal">{title}</p>
      <p className="mt-1 text-[12px] leading-snug text-mute">{body}</p>
      <p className="mt-2 text-[12px]">
        <Link className="underline decoration-amber-signal/60 underline-offset-2" to="/">
          打开舰桥 → 齿轮旋钮（API / Token）
        </Link>
      </p>
    </div>
  );
}
