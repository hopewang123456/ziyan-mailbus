"""Agent 浏览器入口鉴权统一组件 — auth 块解析 + 免密 URL 注入。

边界：mailbus 只管「浏览器入口」鉴权与免密跳转；agent 的 LLM provider 凭据
（cc-switch / DeepSeek 中转 key）归 agent 内部，mailbus 不读取不注入。

- ``resolve_agent_auth()``  → 解析 agent 浏览器鉴权（auth 块显式优先，回退 secrets 自动生成）
- ``build_authed_url()``    → token→?token=、basic→userinfo、header→预留
- ``agent_browser_authed()``→ 是否有浏览器凭据（白名单放行门槛）
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from lib.infra.constants import MAILBUS_ROOT

# auth 块允许的 mode（显式配置）
AUTH_MODES = ("none", "token", "basic", "header")

# 无浏览器 UI 的 agent（不进白名单/URL 生成）
BROWSERLESS_TYPES = ("opencode", "none", "cline")


def _auth_from_block(auth_block: dict, data_dir: str) -> dict:
    """把 auth 块展开为规范 dict（*_ref 引用 secrets.browser_auth.<agent>）。"""
    out = dict(auth_block)
    mode = (out.get("mode") or "none").strip().lower()
    out["mode"] = mode
    # token_ref → secrets
    if out.get("token_ref"):
        try:
            from lib.adapters.config import token_store

            agent_ref = str(out["token_ref"])
            cred = token_store.browser_credentials(data_dir, agent_ref)
            out["token"] = out.get("token") or cred.get("token") or ""
        except Exception:
            pass
    # username_ref / password_ref → secrets
    for src, dst in (("username_ref", "user"), ("password_ref", "password")):
        if out.get(src):
            try:
                from lib.adapters.config import token_store

                agent_ref = str(out[src])
                cred = token_store.browser_credentials(data_dir, agent_ref)
                out[dst] = out.get(dst) or cred.get("password" if src == "password_ref" else "user") or ""
            except Exception:
                pass
    return out


def openclaw_gateway_token() -> str:
    """OpenClaw gateway token：env > openclaw.json gateway.auth；无则 change-me。"""
    env_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if env_token:
        return env_token
    import json

    candidates = [
        str(MAILBUS_ROOT.parent / "openclaw_space" / "data" / ".openclaw" / "openclaw.json"),
        os.path.expanduser("~/.openclaw-data/openclaw.json"),
        os.path.expanduser("~/.openclaw/openclaw.json"),
    ]
    for oc_path in candidates:
        try:
            if os.path.isfile(oc_path):
                with open(oc_path, encoding="utf-8") as f:
                    oc = json.load(f)
                gw = oc.get("gateway", {})
                auth = gw.get("auth", {})
                if auth.get("mode") == "token" and auth.get("token"):
                    return str(auth["token"]).strip()
        except Exception:
            pass
    return "change-me"


def resolve_agent_auth(agent_cfg: dict, agent_id: str, data_dir: str = "") -> dict:
    """解析 agent 浏览器鉴权，返回规范 dict（含 mode/凭据/authed）。"""
    atype = (agent_cfg or {}).get("type", "")
    auth_block = (agent_cfg or {}).get("auth") or {}
    mode = (auth_block.get("mode") or "").strip().lower()

    # 无浏览器 UI 的 agent：不参与
    if atype in BROWSERLESS_TYPES:
        return {"mode": "none", "authed": False}

    # 1) 显式 auth 块
    if mode in ("token", "basic", "header"):
        out = _auth_from_block(auth_block, data_dir)
        # Hermes dashboard：session token 收口在卡片，但 URL 不注入（SPA 记住 / env）
        if atype in ("hermes", "hermes_profile") and mode == "token":
            tok = (out.get("token") or "").strip()
            return {
                "mode": "none",
                "token": tok,
                "authed": bool(tok),
                "session": True,
                "token_ref": auth_block.get("token_ref") or "hermes",
            }
        out["authed"] = mode in ("token", "basic") and bool(
            out.get("token") or out.get("user") or out.get("username")
        )
        return out
    if mode == "none":
        return {"mode": "none", "authed": False}

    # 2) 无显式 auth → 按 type 自动生成（secrets.browser_auth.<agent>，幂等）
    try:
        from lib.adapters.config import token_store

        if atype == "openclaw":
            token = openclaw_gateway_token()
            return {"mode": "token", "token": token, "authed": bool(token and token != "change-me")}
        if atype in ("hermes", "hermes_profile"):
            cred = token_store.ensure_browser_credentials(data_dir, "hermes", mode="token")
            # session token：注入容器 env，URL 不注入；authed=固定 token 已持久化
            return {
                "mode": "none",
                "token": cred.get("token") or "",
                "authed": bool(cred.get("token")),
                "generated": True,
            }
        if atype == "codex":
            cred = token_store.ensure_browser_credentials(data_dir, agent_id, mode="basic")
            # web UI 用 password+cookie 记住免密（不注入 URL）；ttyd -c 由启动脚本注入
            return {
                "mode": "none",
                "user": cred.get("user") or "",
                "password": cred.get("password") or "",
                "authed": bool(cred.get("password")),
                "generated": True,
            }
        if atype == "claude_code":
            cred = token_store.ensure_browser_credentials(data_dir, agent_id, mode="basic")
            return {
                "mode": "basic",
                "user": cred.get("user") or "",
                "password": cred.get("password") or "",
                "authed": bool(cred.get("password")),
                "generated": True,
            }
    except Exception:
        pass
    return {"mode": "none", "authed": False}


def agent_browser_authed(auth: dict | None) -> bool:
    """是否有浏览器凭据（白名单放行门槛）。"""
    if not isinstance(auth, dict):
        return False
    return bool(auth.get("authed"))


def build_authed_url(url: str, auth: dict | None) -> str:
    """按 auth 模式注入凭据：token→?token=、basic→userinfo、header/none→原样。"""
    if not url or not isinstance(auth, dict):
        return url
    mode = (auth.get("mode") or "none").strip().lower()
    if mode == "token":
        token = (auth.get("token") or "").strip()
        if token:
            parsed = urlparse(url)
            query = parse_qs(parsed.query, keep_blank_values=True)
            query["token"] = [token]
            return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    elif mode == "basic":
        user = (auth.get("user") or auth.get("username") or "").strip()
        password = (auth.get("password") or "").strip()
        if user:
            parsed = urlparse(url)
            hostport = parsed.netloc
            if "@" in hostport:
                hostport = hostport.rsplit("@", 1)[1]
            cred = f"{user}:{password}" if password else user
            return urlunparse(parsed._replace(netloc=f"{cred}@{hostport}"))
    # header → 预留反代注入 Authorization header；session/password/none → 不注入
    return url


def ensure_all_browser_credentials(data_dir: str) -> dict[str, str]:
    """启动时幂等预生成全部 agent 浏览器凭据（ttyd -c / Hermes session token）。

    遍历 store/config.json 的 agents：
    - hermes_profile → browser_auth.hermes.token（固定 key，与 hermes_dashboard._session_token 一致）
    - codex / claude_code → browser_auth.<agent_id>.user/password（ttyd Basic Auth）

    已存在的凭据保持原样（跨重启不变）。OpenClaw 不生成（读 env / openclaw.json / auth 块）。
    返回 {agent_id: "token" | "basic"} 摘要，仅供日志。
    """
    from lib.infra.utils import json_read

    import os as _os

    try:
        from lib.adapters.config import token_store

        cfg = json_read(_os.path.join(data_dir, "config.json"), {})
        agents = cfg.get("agents") or {}
        generated: dict[str, str] = {}
        if isinstance(agents, dict):
            for agent_id, rec in agents.items():
                atype = (rec.get("type") or "").strip() if isinstance(rec, dict) else ""
                if atype == "hermes_profile":
                    token_store.ensure_browser_credentials(data_dir, "hermes", mode="token")
                    # per-role secrets for future instance split; dashboard still uses shared hermes key
                    token_store.ensure_browser_credentials(data_dir, agent_id, mode="token")
                    generated.setdefault("hermes", "token")
                    generated[agent_id] = "token"
                elif atype in ("codex", "claude_code"):
                    token_store.ensure_browser_credentials(data_dir, agent_id, mode="basic")
                    generated[agent_id] = "basic"
                elif atype == "openclaw":
                    token_store.ensure_browser_credentials(data_dir, "openclaw_gateway", mode="token")
                    generated.setdefault("openclaw_gateway", "token")
        return generated
    except Exception:
        return {}
