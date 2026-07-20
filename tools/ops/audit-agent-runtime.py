#!/usr/bin/env python3
"""Audit mailbus agents: browser ports, CLI resolve, soul/skills/memory."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"E:/ai_tools/mail")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from lib.platform_runner import docker_argv, probe_http, run  # noqa: E402
from lib.utils import json_read  # noqa: E402
from tools.ops.launch_agent import _merged_launch, _resolve_interactive_cmd  # noqa: E402


def dex(*inner: str, timeout: int = 60) -> str:
    r = run(docker_argv("exec", *inner), timeout=timeout)
    text = ((r.stdout or "") + (r.stderr or "")).strip()
    return text.encode("utf-8", "replace").decode("utf-8", "replace")


def safe_print(s: str) -> None:
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode("ascii", "replace").decode("ascii"))


def main() -> int:
    cfg = json_read(str(ROOT / "store" / "config.json"), {})
    data = str(ROOT / "store")
    agents = list((cfg.get("agents") or {}).keys())

    print("=== Hermes skills/soul/memory in container ===")
    out = dex(
        "docker-agents-hermes-1",
        "bash",
        "-lc",
        "for p in lingzhao lingxi lingjin; do "
        "echo -- $p; "
        "test -d /home/hermes/.hermes/profiles/$p/skills && echo skills_ok || echo skills_BAD; "
        "test -f /home/hermes/.hermes/profiles/$p/SOUL.md && echo soul_ok || echo soul_BAD; "
        "test -f /home/hermes/.hermes/profiles/$p/memories/MEMORY.md && echo mem_ok || echo mem_BAD; "
        "ls /home/hermes/.hermes/profiles/$p/skills 2>/dev/null | head -3; "
        "done; "
        "python3 -c \"from hermes_cli.config import ensure_hermes_home, load_config; "
        "import os; os.environ['HERMES_HOME']='/home/hermes/.hermes'; "
        "ensure_hermes_home(); load_config(); print('hermes_config_OK')\"",
        timeout=90,
    )
    safe_print(out)

    print("\n=== OpenClaw / Dali vault memory ===")
    safe_print(dex("docker-agents-openclaw-1", "bash", "-lc",
              "ls -la /workspace/memory 2>&1 | head -5; "
              "test -f /workspace/MEMORY.md && echo MEMORY_md_ok; "
              "test -f /workspace/SOUL.md && echo SOUL_ok; "
              "ls /workspace/skills 2>&1 | head -5"))
    safe_print(dex("docker-agents-dali-1", "bash", "-lc",
              "ls -la /workspace/opencode/memory 2>&1 | head -5; "
              "test -f /workspace/opencode/MEMORY.md && echo dali_MEMORY_ok; "
              "ls /workspace/opencode/skills 2>&1 | head -5"))

    print("\n=== Browser ports ===")
    ports = {
        "lingzhao": 9120, "lingjin": 9121, "lingxi": 9122, "lingxun": 9125,
        "lingtuo": 9126, "lingzhang": 9127, "xiaoqi": 18789, "yige": 18790,
        "lingxiao": 9240, "lingjian": 9241, "lingyun": 9260, "lingyan": 9261,
    }
    for name, port in ports.items():
        ok = probe_http(f"http://127.0.0.1:{port}/", ok_codes=frozenset({200, 301, 302, 401, 403, 404}))
        print(f"  {name:12} :{port} {'UP' if ok else 'DOWN'}")

    print("\n=== CLI resolve (mailbus) ===")
    for a in sorted(agents):
        m = _merged_launch(cfg, a, "cli")
        try:
            cmd = _resolve_interactive_cmd(a, data, m)
            print(f"  {a:12} {'OK' if cmd else 'EMPTY'} {(cmd or '')[:70]}")
        except Exception as e:
            print(f"  {a:12} ERR {e}")

    print("\n=== Hermes CLI smoke (ensure_hermes_home only) ===")
    # Full chat needs TTY/API; config load is the failure we saw
    smoke = dex(
        "docker-agents-hermes-1",
        "bash",
        "-lc",
        "HERMES_HOME=/home/hermes/.hermes hermes chat --help >/dev/null && echo hermes_cli_bin_OK; "
        "cd /home/hermes && HERMES_HOME=/home/hermes/.hermes "
        "python3 -c \"from hermes_cli.config import ensure_hermes_home; "
        "ensure_hermes_home(); print('ensure_home_OK')\"",
        timeout=60,
    )
    safe_print(smoke)

    print("\n=== launch_agent browser dry (no window) ===")
    import tools.ops.launch_agent as la

    la._start_browser = lambda url: 0
    import lib.claude_browser_launch as cbl

    cbl._launch_url = lambda url: None
    for a in ["lingzhao", "xiaoqi", "lingxiao", "lingyun", "lingjian", "yige", "lingyan"]:
        try:
            rc = la.launch_agent(a, "browser", data)
            print(f"  browser {a}: rc={rc}")
        except Exception as e:
            print(f"  browser {a}: EXC {e}")

    print("\n=== Host vault memory links ===")
    for p in [
        r"E:\Obsidian\Vaults\Agent\memories\lingzhao\MEMORY.md",
        r"E:\Obsidian\Vaults\Agent\memories\xiaoqi\MEMORY.md",
        r"E:\Obsidian\Vaults\Agent\memories\dali\MEMORY.md",
        r"E:\ai_tools\openclaw_space\memory",
        r"E:\ai_tools\opencode\memory",
        r"E:\hermes-data\.hermes\profiles\lingzhao\memories",
    ]:
        pp = Path(p)
        print(f"  {p}: exists={pp.exists()} symlink/junction={pp.is_symlink() or (pp.exists() and bool(pp.stat()))}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
