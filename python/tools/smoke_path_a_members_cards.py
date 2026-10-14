#!/usr/bin/env python3
"""Path A smoke: Members → PATCH Agent cards via settings API → launch via /api/launch.

Does NOT open URLs by hand. Simulates Cockpit card save then roster open browser/cli.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

VAULT = Path(os.environ.get("OBSIDIAN_VAULT", r"E:\Obsidian\Vaults"))
PATH_MAP = VAULT / "Agent" / "_path-map.json"
API = os.environ.get("MAILBUS_API", "http://127.0.0.1:9814")
DATA = str(ROOT / "store")

# Topology defaults (local stack) — also written onto cards
TOPOLOGY = {
    "hermes_profile": {"run_target": "docker", "host": "127.0.0.1"},
    "openclaw": {"run_target": "docker", "host": "127.0.0.1"},
    "opencode": {"run_target": "docker", "host": "127.0.0.1"},
    "codex": {"run_target": "docker", "host": "127.0.0.1"},
    "claude_code": {"run_target": "windows", "host": "127.0.0.1"},
    "cursor": {"run_target": "windows", "host": "127.0.0.1"},
}

PORTS = {
    "lingzhao": 9120,
    "lingjin": 9121,
    "lingtuo": 9122,
    "lingxi": 9123,
    "lingxun": 9125,
    "lingzhang": 9126,
    "xiaoqi": 18789,
    "yige": 18790,
    "lingxiao": 9240,
    "lingjian": 9241,
    "lingyun": 9260,
    "lingyan": 9261,
}

# Native install roots (default env) — from Members/_card + junctions
INSTALL = {
    "hermes_profile": r"E:\ai_tools\docker\mailbus-hermes\.hermes",
    "openclaw": r"E:\ai_tools\docker\openclaw_space",
    "codex": str(Path.home() / ".codex"),
    "claude_code": r"E:\ai_tools",
    "cursor": r"D:\cursor",
    "opencode": r"E:\ai_tools\docker\opencode",
}


def api(method: str, path: str, body: dict | None = None, timeout: float = 60.0) -> tuple[int, dict]:
    url = API.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return e.code, payload
    except Exception as e:
        return 0, {"error": f"{type(e).__name__}: {e}"}


def load_path_map() -> dict:
    return json.loads(PATH_MAP.read_text(encoding="utf-8"))


def members_paths(aid: str, pmap: dict) -> dict:
    """Build custom paths block from Vault Members + path-map."""
    persons = pmap.get("persons") or {}
    frameworks = pmap.get("frameworks") or {}
    vault_root = Path(pmap.get("vault_root") or VAULT)
    person = persons.get(aid) or {}
    fw_key = person.get("framework") or ""
    # map person framework hermes → hermes_profile card type uses hermes framework tree
    fw_map_key = "hermes" if fw_key == "hermes" else fw_key
    fw = frameworks.get(fw_map_key) or {}
    category = fw.get("category") or ""
    config_rel = fw.get("config") or ""
    skills_rel = fw.get("skills") or ""
    person_cat = person.get("category") or ""
    pid = person.get("id") or ""

    def abs_path(*parts: str) -> str:
        p = vault_root.joinpath(*[x for x in parts if x])
        return str(p).replace("/", os.sep)

    fw_config = abs_path(category, config_rel) if category and config_rel else ""
    fw_skills = abs_path(category, skills_rel) if category and skills_rel else ""
    person_root = abs_path(person_cat) if person_cat else ""
    person_config = abs_path(person_cat, f"{pid}1-config") if person_cat and pid else ""
    person_memory = abs_path(person_cat, f"{pid}3-memory") if person_cat and pid else ""

    return {
        "members_root": abs_path(pmap.get("roots", {}).get("members_root") or "Agent/02-members"),
        "framework_config": fw_config,
        "framework_skills": fw_skills,
        "persona": person_root,
        "config": person_config or fw_config,
        "skills": fw_skills,
        "memory": person_memory,
        "path_map_person": person_cat,
    }


def ensure_cursor_agent() -> None:
    """Cursor may be missing from roster — create via store then settings will see it."""
    cfg_path = Path(DATA) / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    agents = cfg.setdefault("agents", {})
    if "cursor" in agents:
        return
    agents["cursor"] = {
        "type": "cursor",
        "role": "IDE 宿主",
        "enabled": True,
        "available": True,
        "auth": {"mode": "none", "note": "Cursor IDE/CLI"},
        "launch": {"has_browser": False, "cli": {"kind": "shell"}},
    }
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("created cursor agent in store (pre-API)")


def patch_agent(aid: str, fields: dict) -> tuple[int, dict]:
    return api("POST", "/api/settings/section/agents", {"agent_id": aid, "fields": fields})


def configure_all_cards(pmap: dict) -> list[str]:
    code, section = api("GET", "/api/settings/section/agents")
    if code != 200:
        raise RuntimeError(f"GET agents failed: {code} {section}")
    items = {it["id"]: it for it in (section.get("agents") or [])}
    configured: list[str] = []

    from lib.adapters.frameworks.framework_discovery import framework_default_install_path

    for aid, it in sorted(items.items()):
        atype = (it.get("type") or "").strip()
        topo = TOPOLOGY.get(atype) or TOPOLOGY.get(
            "hermes_profile" if atype == "hermes" else atype, {"run_target": "windows", "host": "127.0.0.1"}
        )
        paths = members_paths(aid, pmap) if aid in (pmap.get("persons") or {}) else {}
        # cursor not in persons map yet — still point skills/rules to Members cursor tree
        if aid == "cursor" and not paths.get("framework_config"):
            fw = (pmap.get("frameworks") or {}).get("cursor") or {}
            vault_root = Path(pmap.get("vault_root") or VAULT)
            cat = fw.get("category") or ""
            paths = {
                "framework_config": str(vault_root / cat / (fw.get("config") or "")),
                "framework_skills": str(vault_root / cat / (fw.get("skills") or "")),
                "skills": str(vault_root / cat / (fw.get("skills") or "")),
                "rules": str(vault_root / cat / (fw.get("rules") or "")),
                "config": str(vault_root / cat / (fw.get("config") or "")),
            }

        install = (it.get("install_path") or "").strip() or INSTALL.get(atype) or framework_default_install_path(atype)
        fields: dict = {
            "run_target": topo["run_target"],
            "host": topo["host"],
            "install_path": install,
            "custom_paths": True,
            "paths": {k: v for k, v in paths.items() if v},
            "native_config_path": paths.get("framework_config") or paths.get("config") or "",
        }
        if aid in PORTS:
            fields["port"] = PORTS[aid]
            fields["endpoint"] = {"host": topo["host"], "port": PORTS[aid]}

        # keep launch template defaults usable
        launch = dict(it.get("launch") or {})
        if atype in ("hermes_profile", "hermes"):
            launch.setdefault("template", "hermes_dashboard")
            launch["has_browser"] = True
            br = dict(launch.get("browser") or {})
            br["kind"] = "hermes_dashboard"
            if aid in PORTS:
                br["dashboard_port"] = PORTS[aid]
            launch["browser"] = br
        elif atype == "openclaw":
            launch.setdefault("template", "openclaw_gateway")
            launch["has_browser"] = True
            br = dict(launch.get("browser") or {})
            br["kind"] = "openclaw_gateway"
            if aid in PORTS:
                br["gateway_port"] = PORTS[aid]
            launch["browser"] = br
        elif atype == "codex":
            launch.setdefault("template", "codex_docker")
            launch["has_browser"] = True
        elif atype == "claude_code":
            launch.setdefault("template", "claude_host")
            launch["has_browser"] = True
            launch["launch_via_api"] = True
        elif atype == "opencode":
            launch.setdefault("template", "opencode_cli")
            launch["has_browser"] = False
        elif atype == "cursor":
            launch["has_browser"] = False
            launch.setdefault("cli", {"kind": "shell"})
        fields["launch"] = launch

        code, resp = patch_agent(aid, fields)
        ok = code in (200, 201)
        print(f"  PATCH {aid}: HTTP {code} paths={bool(fields.get('paths'))} port={fields.get('port')}")
        if not ok:
            print(f"    ERR {resp}")
        else:
            configured.append(aid)
            if resp.get("auth_required"):
                print(f"    auth_required → {resp.get('obtain_credential_url')}")
        time.sleep(0.05)
    return configured


def realign_hermes_dashboards() -> None:
    """Kill mis-bound dashboards and start-all from card ports (lib mounted in container)."""
    cmds = [
        "pkill -f 'hermes_cli.main.*dashboard' || true",
        "sleep 2",
        "cd /mailbus && python3.12 -m lib.adapters.frameworks.hermes_dashboard start-all",
    ]
    inner = " && ".join(cmds)
    r = subprocess.run(
        ["wsl", "-d", "Ubuntu", "-e", "bash", "-lc",
         f"docker exec docker-agents-hermes-1 bash -lc {json.dumps(inner)}"],
        capture_output=True,
        text=True,
        timeout=240,
    )
    print((r.stdout or "")[-2000:])
    if r.returncode != 0:
        print("hermes realign stderr:", (r.stderr or "")[-800:])


def launch_all(agents: list[str], pmap: dict) -> list[dict]:
    results = []
    persons = set((pmap.get("persons") or {}).keys()) | {"cursor"}
    for aid in agents:
        if aid not in persons and aid != "cursor":
            pass
        # browser
        code, resp = api("POST", "/api/launch", {"agent": aid, "mode": "browser"}, timeout=120)
        row = {"agent": aid, "browser_http": code, "browser": resp}
        print(f"  LAUNCH browser {aid}: {code} {resp.get('status') or resp.get('error')} {resp.get('url') or resp.get('message') or ''}")
        time.sleep(0.3)
        # cli
        code2, resp2 = api("POST", "/api/launch", {"agent": aid, "mode": "cli"}, timeout=120)
        row["cli_http"] = code2
        row["cli"] = resp2
        print(f"  LAUNCH cli {aid}: {code2} {resp2.get('status') or resp2.get('error')} {resp2.get('message') or ''}")
        results.append(row)
        time.sleep(0.4)
    return results


def probe_ports() -> None:
    print("=== probe published ports ===")
    for aid, port in sorted(PORTS.items(), key=lambda x: x[1]):
        url = f"http://127.0.0.1:{port}/"
        if aid in ("xiaoqi", "yige"):
            from lib.adapters.config.browser_auth import openclaw_gateway_token

            url = f"http://127.0.0.1:{port}/chat?token={openclaw_gateway_token()}"
        code, _ = api("GET", url.replace(API, "") if url.startswith(API) else "/")
        # direct probe
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=4) as resp:
                print(f"  {aid:10} {resp.status} {url}")
        except urllib.error.HTTPError as e:
            print(f"  {aid:10} {e.code} {url}")
        except Exception as e:
            print(f"  {aid:10} ERR:{type(e).__name__} {url}")


def main() -> int:
    os.chdir(ROOT)
    print("=== Path A: Members → Agent cards (API) → /api/launch ===")
    print("path-map:", PATH_MAP)
    print("API:", API)

    st, body = api("GET", "/api/status")
    if st != 200:
        print("mailbus not up:", st, body)
        return 1
    print("mailbus ok, agents=", body.get("agents"))

    ensure_cursor_agent()
    # reload mailbus may need file watch — status already saw agents

    pmap = load_path_map()
    print("\n=== configure cards from Members ===")
    configured = configure_all_cards(pmap)
    print(f"configured {len(configured)} agents")

    # re-synthesize instances via a no-op path: GET section synthesizes in memory;
    # force persist instances by clearing then GET+write through patch of one agent
    from lib.adapters.config.agent_instances import synthesize_instances_from_agents

    cfg_path = Path(DATA) / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg.pop("agent_instances", None)
    for a in (cfg.get("agents") or {}).values():
        if isinstance(a, dict):
            a.pop("instance_id", None)
    cfg = synthesize_instances_from_agents(cfg)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("instances:", len(cfg.get("agent_instances") or {}))

    print("\n=== realign hermes dashboards to card ports ===")
    realign_hermes_dashboards()

    print("\n=== launch via /api/launch (card path) ===")
    results = launch_all(configured, pmap)

    probe_ports()

    out = ROOT / "store" / "reports" / "path-a-members-card-smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"configured": configured, "launches": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("report:", out)

    # summary
    br_ok = sum(1 for r in results if r.get("browser_http") == 200 and (r.get("browser") or {}).get("status") == "ok")
    cli_ok = sum(1 for r in results if r.get("cli_http") == 200 and (r.get("cli") or {}).get("status") == "ok")
    print(f"\nSUMMARY browser ok {br_ok}/{len(results)} · cli ok {cli_ok}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
