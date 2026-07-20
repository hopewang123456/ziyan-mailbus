#!/usr/bin/env python3
"""Full audit of 13 mailbus agents: memory / skills / soul / role / browser / CLI."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(r"E:/ai_tools/mail")
VAULT = Path(r"E:/Obsidian/Vaults/Agent")
HERMES = Path(r"E:/hermes-data/.hermes")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from lib.platform_runner import docker_argv, probe_http, run  # noqa: E402
from lib.utils import json_read  # noqa: E402
from tools.ops.launch_agent import _merged_launch, _resolve_interactive_cmd  # noqa: E402

PERSON_ROLE = {
    "dali": ("大力", "coding-executor", "opencode"),
    "lingjian": ("灵鉴", "code-reviewer", "codex"),
    "lingjin": ("灵瑾", "security-auditor", "hermes"),
    "lingtuo": ("灵拓", "market-expansion", "hermes"),
    "lingxi": ("灵犀", "tech-radar", "hermes"),
    "lingxiao": ("灵霄", "tech-lead", "codex"),
    "lingxun": ("灵巡", "patroller", "hermes"),
    "lingyan": ("灵验", "test-engineer", "claude"),
    "lingyun": ("灵云", "coding-pro", "claude"),
    "lingzhang": ("灵账", "finance-followup", "hermes"),
    "lingzhao": ("灵昭", "spec-designer", "hermes"),
    "xiaoqi": ("小七", "orchestrator", "openclaw"),
    "yige": ("一哥", "operations", "openclaw"),
}

BROWSER_PORTS = {
    "lingzhao": 9120,
    "lingjin": 9121,
    "lingxi": 9122,
    "lingxun": 9125,
    "lingtuo": 9126,
    "lingzhang": 9127,
    "xiaoqi": 18789,
    "yige": 18790,
    "lingxiao": 9240,
    "lingjian": 9241,
    "lingyun": 9260,
    "lingyan": 9261,
    # dali: CLI only
}

FULL_LIBRARY_ROLES = {"coding-executor", "market-expansion", "finance-followup", "orchestrator", "operations"}


def dex(container: str, script: str, timeout: int = 45) -> tuple[int, str]:
    r = run(docker_argv("exec", container, "bash", "-lc", script), timeout=timeout)
    text = ((r.stdout or "") + (r.stderr or "")).encode("ascii", "replace").decode("ascii")
    return r.returncode, text.strip()


def is_reparse(p: Path) -> bool:
    if not p.exists():
        return False
    try:
        import ctypes

        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
        return attrs != -1 and bool(attrs & 0x400)
    except Exception:
        return p.is_symlink()


def check_host(agent: str, fw: str, role: str) -> dict:
    out = {"memory": "?", "skills": "?", "soul": "?", "role_view": "?"}
    mem = VAULT / "memories" / agent
    out["memory"] = "OK" if (mem / "MEMORY.md").is_file() else "MISS"
    if fw == "hermes":
        prof = HERMES / "profiles" / agent
        soul = prof / "SOUL.md"
        skills = prof / "skills"
        memories = prof / "memories"
        out["soul"] = "OK" if soul.is_file() else "MISS"
        if skills.exists() and (is_reparse(skills) or skills.is_dir()):
            # resolve content
            try:
                n = len(list(skills.iterdir()))
                out["skills"] = f"OK({n})" if n > 0 else "EMPTY"
            except OSError:
                out["skills"] = "BROKEN"
        else:
            out["skills"] = "MISS"
        out["mem_link"] = "OK" if is_reparse(memories) or (memories / "MEMORY.md").exists() else "MISS"
        view = VAULT / "skills" / "views" / "roles" / role
        lib = VAULT / "skills" / "library"
        target = lib if role in FULL_LIBRARY_ROLES else view
        out["role_view"] = "OK" if target.exists() else "MISS"
    elif fw == "openclaw":
        space = Path(r"E:/ai_tools/openclaw_space")
        out["soul"] = "OK" if (space / "SOUL.md").is_file() else "MISS"
        skills = Path(r"E:/Obsidian/Vaults/Agent/skills/library/openclaw")
        out["skills"] = "OK" if skills.exists() and any(skills.iterdir()) else "MISS"
        mem_link = space / "memory" if agent == "xiaoqi" else space / "a-yige" / "memory"
        out["mem_link"] = "OK" if is_reparse(mem_link) or mem_link.exists() else "MISS"
        out["role_view"] = "OK" if (VAULT / "skills" / "library").exists() else "MISS"
    elif fw == "codex":
        # Codex: SOUL may live in workspace or team-pack overlay
        ws = Path(rf"E:/ai_tools/{agent}")
        soul_candidates = [
            ws / "SOUL.md",
            VAULT / "skills" / "team-pack" / "roles" / "overlays" / agent / "SKILL.md",
            ROOT / "skills" / "roles" / "overlays" / agent / "SKILL.md",
        ]
        out["soul"] = "OK" if any(p.is_file() for p in soul_candidates) else "MISS"
        skills = Path(r"E:/.codex/skills")
        out["skills"] = "OK" if skills.exists() else "MISS"
        mem_ok = (VAULT / "memories" / agent / "MEMORY.md").is_file()
        out["memory"] = "OK" if mem_ok else "MISS"
        out["mem_link"] = "OK" if is_reparse(ws / "memory") or mem_ok else "MISS"
        view = VAULT / "skills" / "views" / "roles" / role
        out["role_view"] = "OK" if view.exists() or role in FULL_LIBRARY_ROLES else "MISS"
    elif fw == "claude":
        # Claude home under user profile
        for base in (
            Path(rf"C:/Users/hopew/.claude-{agent}"),
            Path(os.path.expanduser(f"~/.claude-{agent}")),
        ):
            if (base / "CLAUDE.md").is_file() or (base / "SOUL.md").is_file():
                out["soul"] = "OK"
                break
        else:
            ov = VAULT / "skills" / "team-pack" / "roles" / "overlays" / agent / "SKILL.md"
            out["soul"] = "OK" if ov.is_file() else "MISS"
        view = VAULT / "skills" / "views" / "roles" / role
        out["skills"] = "OK" if view.exists() else "MISS"
        mem_ok = (VAULT / "memories" / agent / "MEMORY.md").is_file()
        out["memory"] = "OK" if mem_ok else "MISS"
        out["mem_link"] = "OK" if any(
            is_reparse(Path(rf"C:/Users/hopew/.claude-{agent}") / "memory") for _ in [0]
        ) or mem_ok else "MISS"
        out["role_view"] = out["skills"]
    elif fw == "opencode":
        oc = Path(r"E:/ai_tools/opencode")
        out["soul"] = "OK" if (oc / "AGENTS.md").is_file() or (VAULT / "skills" / "team-pack" / "roles" / "overlays" / "dali" / "SKILL.md").is_file() else "MISS"
        out["skills"] = "OK" if (oc / "skills").exists() or (VAULT / "skills" / "02-agent-specific" / "opencode").exists() else "MISS"
        out["mem_link"] = "OK" if is_reparse(oc / "memory") else "MISS"
        out["role_view"] = "OK"
    return out


def check_container(agent: str, fw: str) -> dict:
    out = {}
    if fw == "hermes":
        rc, text = dex(
            "docker-agents-hermes-1",
            f"p=/home/hermes/.hermes/profiles/{agent}; "
            f"test -d $p/skills && echo skills_ok || echo skills_BAD; "
            f"test -f $p/SOUL.md && echo soul_ok || echo soul_BAD; "
            f"test -f $p/memories/MEMORY.md && echo mem_ok || echo mem_BAD; "
            f"python3 -c \"from hermes_cli.config import ensure_hermes_home; "
            f"import os; os.environ['HERMES_HOME']='/home/hermes/.hermes'; "
            f"os.environ['HERMES_PROFILE']='{agent}'; ensure_hermes_home(); print('cfg_ok')\" 2>/dev/null || echo cfg_BAD",
            timeout=60,
        )
        out["skills"] = "OK" if "skills_ok" in text else "BAD"
        out["soul"] = "OK" if "soul_ok" in text else "BAD"
        out["memory"] = "OK" if "mem_ok" in text else "BAD"
        out["config"] = "OK" if "cfg_ok" in text else "BAD"
    elif fw == "openclaw":
        state = f"/workspace/data/.openclaw-{agent}"
        rc, text = dex(
            "docker-agents-openclaw-1",
            f"test -f /workspace/SOUL.md && echo soul_ok; "
            f"test -d /workspace/skills && echo skills_ok; "
            f"test -d /workspace/memory -o -L /workspace/memory && echo mem_ok; "
            f"test -f {state}/openclaw.json && echo state_ok || echo state_BAD",
        )
        out["soul"] = "OK" if "soul_ok" in text else "BAD"
        out["skills"] = "OK" if "skills_ok" in text else "BAD"
        out["memory"] = "OK" if "mem_ok" in text else "BAD"
        out["state"] = "OK" if "state_ok" in text else "BAD"
    elif fw == "codex":
        c = f"docker-agents-{agent}-1"
        rc, text = dex(c, "test -d /home/node/.codex/skills && echo skills_ok || echo skills_BAD; which codex && echo bin_ok")
        out["skills"] = "OK" if "skills_ok" in text else "BAD"
        out["bin"] = "OK" if "bin_ok" in text else "BAD"
    elif fw == "claude":
        out["note"] = "host/wsl ttyd"
    elif fw == "opencode":
        rc, text = dex(
            "docker-agents-dali-1",
            "test -d /workspace/opencode/skills && echo skills_ok; "
            "test -f /workspace/opencode/MEMORY.md && echo mem_ok; "
            "test -d /workspace/opencode/memory -o -L /workspace/opencode/memory && echo memdir_ok; "
            "which opencode >/dev/null && echo bin_ok",
        )
        out["skills"] = "OK" if "skills_ok" in text else "BAD"
        out["memory"] = "OK" if "mem_ok" in text or "memdir_ok" in text else "BAD"
        out["bin"] = "OK" if "bin_ok" in text else "BAD"
    return out


def main() -> int:
    cfg = json_read(str(ROOT / "store" / "config.json"), {})
    data = str(ROOT / "store")
    agents_cfg = cfg.get("agents") or {}

    # ensure hermes dashboards once
    ensure = ROOT / "docker-agents" / "ensure-hermes-dashboards.sh"
    if ensure.is_file():
        run(["wsl", "-e", "bash", str(ensure).replace("\\", "/").replace("E:", "/mnt/e")], timeout=120)

    rows = []
    print("=" * 100)
    print(f"{'agent':10} {'role':20} {'fw':8} {'browser':8} {'cli':6} {'soul':6} {'skills':10} {'memory':8} {'ctr':20}")
    print("=" * 100)

    import tools.ops.launch_agent as la
    import lib.claude_browser_launch as cbl

    la._start_browser = lambda url: 0
    cbl._launch_url = lambda url: None

    fails = []
    for agent in sorted(PERSON_ROLE):
        display, role, fw = PERSON_ROLE[agent]
        acfg = agents_cfg.get(agent) or {}
        host = check_host(agent, fw, role)
        ctr = check_container(agent, fw)

        # browser
        browser = "N/A"
        if agent == "dali":
            browser = "N/A"
        else:
            port = BROWSER_PORTS.get(agent)
            if port and probe_http(
                f"http://127.0.0.1:{port}/",
                ok_codes=frozenset({200, 301, 302, 401, 403, 404}),
            ):
                browser = "UP"
            else:
                # try launch
                try:
                    rc = la.launch_agent(agent, "browser", data)
                    browser = "UP" if rc == 0 else f"FAIL({rc})"
                except Exception as e:
                    browser = f"ERR"
                    fails.append((agent, "browser", str(e)[:80]))

        # cli resolve
        merged = _merged_launch(cfg, agent, "cli")
        try:
            cmd = _resolve_interactive_cmd(agent, data, merged)
            cli = "OK" if cmd else "EMPTY"
            if not cmd:
                fails.append((agent, "cli", "empty command"))
        except Exception as e:
            cli = "ERR"
            fails.append((agent, "cli", str(e)[:80]))

        # store archetype / type
        store_type = acfg.get("type", "?")
        launch = acfg.get("launch") or {}

        soul = host.get("soul", "?")
        skills = host.get("skills", "?")
        memory = host.get("memory", "?")
        # prefer container checks when present
        if "soul" in ctr and ctr["soul"] == "BAD":
            soul = "BAD"
            fails.append((agent, "soul", "container"))
        if "skills" in ctr and ctr["skills"] == "BAD":
            skills = "BAD"
            fails.append((agent, "skills", "container"))
        if "memory" in ctr and ctr["memory"] == "BAD":
            memory = "BAD"
            fails.append((agent, "memory", "container"))
        if host.get("role_view") == "MISS":
            fails.append((agent, "role_view", role))

        ctr_s = ",".join(f"{k}={v}" for k, v in ctr.items())[:20]
        print(
            f"{agent:10} {role:20} {fw:8} {browser:8} {cli:6} {soul:6} {skills:10} {memory:8} {ctr_s:20}"
        )
        rows.append(
            {
                "agent": agent,
                "display": display,
                "role": role,
                "fw": fw,
                "store_type": store_type,
                "browser": browser,
                "cli": cli,
                "soul": soul,
                "skills": skills,
                "memory": memory,
                "mem_link": host.get("mem_link"),
                "role_view": host.get("role_view"),
                "container": ctr,
                "launch_template": launch.get("template"),
            }
        )

    print("=" * 100)
    bad = [r for r in rows if any(
        str(r[k]).startswith(("BAD", "MISS", "EMPTY", "FAIL", "ERR", "WEAK", "BROKEN"))
        for k in ("browser", "cli", "soul", "skills", "memory", "role_view")
        if r.get(k) not in (None, "N/A", "WEAK")  # WEAK alone ok for codex/claude memory
    ) or r["browser"].startswith(("FAIL", "ERR")) or r["cli"] in ("EMPTY", "ERR")
        or r["soul"] in ("BAD", "MISS") or r["skills"] in ("BAD", "MISS", "EMPTY", "BROKEN")
        or r["memory"] in ("BAD", "MISS") or r.get("role_view") == "MISS"]

    # soften: WEAK memory for codex/claude is warning not fail if vault stub exists
    report_path = VAULT / "memories" / "_audit-13-agents.json"
    report_path.write_text(json.dumps({"rows": rows, "fails": fails}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nFAIL/WARN agents: {len(bad)}/{len(rows)}")
    for r in bad:
        issues = []
        for k in ("browser", "cli", "soul", "skills", "memory", "role_view", "mem_link"):
            v = r.get(k)
            if v in ("BAD", "MISS", "EMPTY", "BROKEN") or (isinstance(v, str) and v.startswith(("FAIL", "ERR"))):
                issues.append(f"{k}={v}")
            if v == "WEAK":
                issues.append(f"{k}=WEAK")
        print(f"  ! {r['agent']}: {', '.join(issues)}")
    for f in fails:
        print(f"  fail-detail: {f}")
    print(f"\nReport: {report_path}")
    return 1 if any(
        r["browser"].startswith(("FAIL", "ERR")) or r["cli"] in ("EMPTY", "ERR")
        or r["soul"] in ("BAD", "MISS") or r["skills"] in ("BAD", "MISS", "EMPTY", "BROKEN")
        or r["memory"] in ("BAD", "MISS") or r.get("role_view") == "MISS"
        for r in rows if r["agent"] != "dali" or True
    ) else 0


if __name__ == "__main__":
    # dali browser N/A is fine
    raise SystemExit(main())
