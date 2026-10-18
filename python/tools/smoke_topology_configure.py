"""Configure agent cards to match local topology and smoke browser/CLI."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "shared" / "store"
CFG = DATA / "config.json"

# Topology (user recollection + live docker ps)
# hermes/openclaw/opencode/codex → docker published on host loopback
# claude_code/cursor → windows host
TOPOLOGY = {
    "hermes": {"run_target": "docker", "host": "127.0.0.1"},
    "hermes_profile": {"run_target": "docker", "host": "127.0.0.1"},
    "openclaw": {"run_target": "docker", "host": "127.0.0.1"},
    "opencode": {"run_target": "docker", "host": "127.0.0.1"},
    "codex": {"run_target": "docker", "host": "127.0.0.1"},  # containers via WSL docker
    "claude_code": {"run_target": "windows", "host": "127.0.0.1"},
    "cursor": {"run_target": "windows", "host": "127.0.0.1"},
}

# Known port map from compose / roster
PORT_HINTS = {
    "lingzhao": 9120,
    "lingjin": 9121,
    "lingtuo": 9122,
    "lingxi": 9123,
    "lingxun": 9125,
    "lingzhang": 9126,
    "xiaoqi": 18789,
    "yige": 18790,
    # compose: 924x→7681 codex-ui, 925x→7682 ttyd/web; UI often down → prefer ttyd
    "lingxiao": 9240,
    "lingjian": 9241,
    "lingyan": 9261,
    "lingyun": 9260,
}


def http_code(url: str, timeout: float = 4.0) -> tuple[int | str, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, url
    except urllib.error.HTTPError as e:
        return e.code, url
    except Exception as e:
        return f"ERR:{type(e).__name__}", url


def which(cmd: str) -> str:
    from shutil import which as w

    return w(cmd) or ""


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "python"))

    from lib.adapters.config.browser_auth import build_authed_url, ensure_all_browser_credentials, resolve_agent_auth
    from lib.adapters.config.agent_instances import synthesize_instances_from_agents
    from lib.adapters.runtime.cred_delivery import apply_instance_endpoint, sync_browser_credentials_to_env

    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    agents = cfg.get("agents") or {}
    ensure_all_browser_credentials(str(DATA))
    sync_browser_credentials_to_env(str(DATA))

    print("=== patch agent cards ===")
    for aid, rec in list(agents.items()):
        if not isinstance(rec, dict):
            continue
        atype = (rec.get("type") or "").strip()
        topo = TOPOLOGY.get(atype)
        if not topo:
            print(f"  skip {aid} type={atype}")
            continue
        rec["run_target"] = topo["run_target"]
        rec["host"] = topo["host"]
        if aid in PORT_HINTS:
            rec["port"] = PORT_HINTS[aid]
        # note for codex: docker under WSL
        if atype == "codex":
            rec.setdefault("topology_note", "browser via docker ports; docker engine on WSL")
        agents[aid] = rec
        print(f"  {aid}: type={atype} rt={rec['run_target']} {rec.get('host')}:{rec.get('port')}")

    cfg["agents"] = agents
    cfg = synthesize_instances_from_agents(cfg)
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("instances:", len(cfg.get("agent_instances") or {}))

    print("\n=== browser probe (authed URL when possible) ===")
    for aid, rec in agents.items():
        if not isinstance(rec, dict):
            continue
        atype = (rec.get("type") or "").strip()
        if atype in ("opencode", "none", "cline"):
            print(f"  {aid}: no browser (CLI-only type)")
            continue
        port = rec.get("port") or PORT_HINTS.get(aid)
        host = rec.get("host") or "127.0.0.1"
        if not port:
            print(f"  {aid}: skip (no port)")
            continue
        path = "/"
        if atype == "openclaw":
            path = "/chat"
        elif atype in ("hermes", "hermes_profile"):
            path = "/"
        url = f"http://{host}:{port}{path}"
        auth = resolve_agent_auth(rec, aid, str(DATA))
        url = build_authed_url(url, auth)
        url = apply_instance_endpoint(rec, url)
        # strip userinfo for probe if causes issues — still try
        code, _ = http_code(url.split("@")[-1] if "://" in url and "@" in url.split("://", 1)[-1] else url)
        # simpler: probe without secrets in URL for hermes (session not in URL)
        probe = f"http://{host}:{port}{path}"
        if atype == "openclaw" and auth.get("token"):
            probe = f"http://{host}:{port}/chat?token={auth['token']}"
        code, _ = http_code(probe)
        print(f"  {aid}: HTTP {code}  {probe}")

    print("\n=== CLI presence ===")
    checks = [
        ("claude", which("claude") or which("claude.exe")),
        ("cursor", which("cursor") or which("cursor.cmd")),
        ("codex (wsl)", ""),
        ("docker", which("docker") or which("docker.exe")),
    ]
    # wsl codex
    try:
        r = subprocess.run(
            ["wsl", "-d", "Ubuntu", "-e", "bash", "-lc", "command -v codex || command -v npx"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        checks[2] = ("codex (wsl)", (r.stdout or "").strip() or f"exit={r.returncode}")
    except Exception as e:
        checks[2] = ("codex (wsl)", f"ERR {e}")

    for name, path in checks:
        print(f"  {name}: {path or 'NOT FOUND'}")

    # docker exec smoke for hermes/openclaw/opencode
    print("\n=== docker exec smoke ===")
    for cname, cmd in [
        ("docker-agents-hermes-1", "which hermes || ls /home/hermes 2>/dev/null | head -3"),
        ("docker-agents-openclaw-1", "which openclaw || which node || echo ok"),
        ("docker-agents-opencode-1", "which opencode || which node || echo ok"),
        ("docker-agents-codex-web-1", "which node || echo ok"),
    ]:
        try:
            r = subprocess.run(
                ["wsl", "-d", "Ubuntu", "-e", "docker", "exec", cname, "bash", "-lc", cmd],
                capture_output=True,
                text=True,
                timeout=25,
            )
            out = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[:2]
            print(f"  {cname}: exit={r.returncode} {out}")
        except Exception as e:
            print(f"  {cname}: ERR {e}")

    print("\n=== mailbus status ===")
    code, _ = http_code("http://127.0.0.1:9814/api/status")
    print(f"  /api/status → {code}")

    print("\nDONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
