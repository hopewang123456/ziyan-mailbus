"""Smoke: CredDelivery env sync + agent_instances synthesize + auth gate URL."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "shared" / "store"


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "python"))

    from lib.adapters.config.agent_instances import synthesize_instances_from_agents
    from lib.adapters.config.auth_policy import (
        agent_requires_browser_auth,
        raw_browser_entry_url,
    )
    from lib.adapters.config.browser_auth import ensure_all_browser_credentials, resolve_agent_auth
    from lib.adapters.runtime.cred_delivery import (
        resolve_codex_ui_password,
        resolve_openclaw_token,
        sync_browser_credentials_to_env,
    )

    print("=== Ops ensure credentials ===")
    print(ensure_all_browser_credentials(str(DATA)))

    print("=== CredDelivery sync_to_env ===")
    # clear change-me to prove sync
    if os.environ.get("OPENCLAW_GATEWAY_TOKEN") == "change-me":
        os.environ.pop("OPENCLAW_GATEWAY_TOKEN", None)
    applied = sync_browser_credentials_to_env(str(DATA))
    print("applied keys:", sorted(applied.keys()))
    oc = resolve_openclaw_token(str(DATA))
    print("openclaw token present:", bool(oc and oc != "change-me"), "len=", len(oc or ""))
    pw = resolve_codex_ui_password(str(DATA))
    print("codex ui password present:", bool(pw), "len=", len(pw or ""))

    cfg_path = DATA / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    syn = synthesize_instances_from_agents(cfg)
    inst = syn.get("agent_instances") or {}
    print("=== agent_instances ===")
    print("count:", len(inst))
    for iid, rec in list(inst.items())[:8]:
        print(f"  {iid}: type={rec.get('type')} roles={rec.get('role_ids')}")

    print("=== sample auth resolve ===")
    agents = cfg.get("agents") or {}
    for aid in ("xiaoqi", "lingzhao", "lingxiao", "lingyan", "dali"):
        if aid not in agents:
            continue
        ac = agents[aid]
        at = ac.get("type")
        auth = resolve_agent_auth(ac, aid, str(DATA))
        need = agent_requires_browser_auth(str(at), ac)
        url = raw_browser_entry_url(str(DATA), aid, ac)
        print(
            f"  {aid}\ttype={at}\tneed_auth={need}\tauthed={auth.get('authed')}\t"
            f"obtain={url}"
        )

    print("=== smoke OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
