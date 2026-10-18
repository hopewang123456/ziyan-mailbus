"""Ops0: ensure browser credentials + write auth refs onto agent cards."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "shared" / "store"
CFG_PATH = DATA / "config.json"


def main() -> None:
    from lib.adapters.config import token_store
    from lib.adapters.config.browser_auth import (
        ensure_all_browser_credentials,
        openclaw_gateway_token,
        resolve_agent_auth,
    )

    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    agents = cfg.get("agents") or {}
    if not isinstance(agents, dict):
        raise SystemExit("no agents")

    summary = ensure_all_browser_credentials(str(DATA))
    print("ensure_all:", summary)

    # OpenClaw: persist gateway token into secrets + auth block if non-change-me
    oc_token = openclaw_gateway_token()
    if oc_token and oc_token != "change-me":
        token_store.ensure_browser_credentials(str(DATA), "openclaw_gateway", mode="token", token=oc_token)
    else:
        # generate stable team token for openclaw browser entry if none
        cred = token_store.ensure_browser_credentials(str(DATA), "openclaw_gateway", mode="token")
        oc_token = cred.get("token") or ""
        print("openclaw_gateway token ensured (set OPENCLAW_GATEWAY_TOKEN or openclaw.json to override)")

    patched = 0
    rows: list[dict] = []
    for aid, rec in agents.items():
        if not isinstance(rec, dict):
            continue
        atype = (rec.get("type") or "").strip()
        auth = dict(rec.get("auth") or {}) if isinstance(rec.get("auth"), dict) else {}
        before = dict(auth)

        if atype in ("hermes", "hermes_profile"):
            # shared hermes session token; card points via token_ref; mode none is auto path —
            # store explicit auth for Cockpit visibility without forcing URL inject
            auth = {
                "mode": "token",
                "token_ref": "hermes",
                "note": "Hermes dashboard session; env HERMES_DASHBOARD_SESSION_TOKEN; first login may remember",
            }
        elif atype == "openclaw":
            auth = {
                "mode": "token",
                "token_ref": "openclaw_gateway",
                "note": "OpenClaw gateway ?token=; also set OPENCLAW_GATEWAY_TOKEN in env for container",
            }
        elif atype == "codex":
            auth = {
                "mode": "basic",
                "username_ref": aid,
                "password_ref": aid,
                "note": "Codex ttyd basic + UI password from secrets; cookie may remember after first login",
            }
        elif atype == "claude_code":
            auth = {
                "mode": "basic",
                "username_ref": aid,
                "password_ref": aid,
                "note": "Claude ttyd Basic Auth",
            }
        elif atype in ("opencode", "cline", "none"):
            auth = {"mode": "none", "note": "no browser entry"}
        else:
            # keep existing or none
            if not auth:
                auth = {"mode": "none"}

        # ensure per-agent secrets for basic types
        if atype in ("codex", "claude_code"):
            token_store.ensure_browser_credentials(str(DATA), aid, mode="basic")
        if atype in ("hermes", "hermes_profile"):
            token_store.ensure_browser_credentials(str(DATA), "hermes", mode="token")

        rec["auth"] = auth
        if auth != before:
            patched += 1

        resolved = resolve_agent_auth(rec, aid, str(DATA))
        rows.append(
            {
                "id": aid,
                "type": atype,
                "run_target": rec.get("run_target") or "windows",
                "enabled": rec.get("enabled"),
                "auth_mode": (auth.get("mode") or ""),
                "authed": bool(resolved.get("authed")),
                "resolved_mode": resolved.get("mode"),
            }
        )

    cfg["agents"] = agents

    # 同步实例卡 auth（按 type，不写明文 token）
    instances = cfg.get("agent_instances") if isinstance(cfg.get("agent_instances"), dict) else {}
    inst_patched = 0
    for iid, irec in list(instances.items()):
        if not isinstance(irec, dict):
            continue
        atype = (irec.get("type") or "").strip()
        iauth = dict(irec.get("auth") or {}) if isinstance(irec.get("auth"), dict) else {}
        before_i = dict(iauth)
        if atype in ("hermes", "hermes_profile"):
            iauth = {
                "mode": "token",
                "token_ref": "hermes",
                "note": "Hermes dashboard session; env HERMES_DASHBOARD_SESSION_TOKEN",
            }
            token_store.ensure_browser_credentials(str(DATA), "hermes", mode="token")
        elif atype == "openclaw":
            iauth = {
                "mode": "token",
                "token_ref": "openclaw_gateway",
                "note": "OpenClaw gateway token",
            }
            token_store.ensure_browser_credentials(str(DATA), "openclaw_gateway", mode="token")
        elif atype == "codex":
            # 角色级 basic：挂第一个 role 的 ref；无角色则用实例 id
            roles = irec.get("role_ids") if isinstance(irec.get("role_ids"), list) else []
            ref = str(roles[0]) if roles else iid
            iauth = {
                "mode": "basic",
                "username_ref": ref,
                "password_ref": ref,
                "note": "Codex ttyd basic",
            }
            token_store.ensure_browser_credentials(str(DATA), ref, mode="basic")
        elif atype == "claude_code":
            roles = irec.get("role_ids") if isinstance(irec.get("role_ids"), list) else []
            ref = str(roles[0]) if roles else iid
            iauth = {
                "mode": "basic",
                "username_ref": ref,
                "password_ref": ref,
                "note": "Claude ttyd Basic Auth",
            }
            token_store.ensure_browser_credentials(str(DATA), ref, mode="basic")
        elif atype in ("opencode", "cline", "none", "cursor"):
            iauth = {"mode": "none", "note": "no browser entry / optional"}
        else:
            if not iauth:
                iauth = {"mode": "none"}
        irec["auth"] = iauth
        if iauth != before_i:
            inst_patched += 1
        instances[iid] = irec
    cfg["agent_instances"] = instances

    CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"patched_auth_blocks={patched} agents={len(rows)} instances_patched={inst_patched}")

    out = DATA / "ops0-browser-auth-summary.json"
    # do not write secrets — only summary
    out.write_text(json.dumps({"agents": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("summary ->", out)

    ba = (token_store.read_secrets(str(DATA)).get("browser_auth") or {})
    print("browser_auth keys:", sorted(ba.keys()))

    for r in rows:
        print(
            f"{r['id']}\t{r['type']}\tauthed={r['authed']}\t"
            f"card={r['auth_mode']}\tresolved={r['resolved_mode']}\trt={r['run_target']}"
        )


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
