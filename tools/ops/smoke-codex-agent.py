#!/usr/bin/env python3
"""Codex agent 冒烟 — DeepSeek 网关 + AgentMemory + 人设 + 落盘探针。

用法（WSL）:
  python3 tools/tools/ops/smoke-codex-agent.py --container docker-agents-lingxiao-1
  python3 tools/tools/ops/smoke-codex-agent.py --container docker-agents-lingjian-1
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap


def run(cmd: list[str], *, timeout: int = 120) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--container", required=True)
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()
    c = args.container
    fails = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal fails
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            fails += 1

    print(f"== smoke codex @ {c} ==")

    code, out, err = run(["docker", "exec", c, "codex", "--version"])
    check("codex CLI", code == 0 and "codex" in (out + err).lower(), (out or err).strip())

    code, out, _ = run(["docker", "exec", c, "bash", "-lc", "curl -sf http://127.0.0.1:3000/health"])
    check("deepseek gateway /health", code == 0, (out or "")[:120])

    code, out, _ = run(["docker", "exec", c, "bash", "-lc", "curl -sf http://iii-engine:3111/agentmemory/health"])
    check("agentmemory health", code == 0, (out or "")[:120])

    code, out, _ = run(["docker", "exec", c, "bash", "-lc", "grep -q agentmemory /home/node/.codex/config.toml && echo ok"])
    check("config.toml MCP block", code == 0 and "ok" in out)

    code, out, _ = run(["docker", "exec", c, "bash", "-lc", "grep -q developer_instructions /home/node/.codex/config.toml && echo ok"])
    check("config.toml identity", code == 0 and "ok" in out)

    code, out, _ = run(["docker", "exec", c, "bash", "-lc", "grep -q model_catalog_json /home/node/.codex/config.toml && test -f /home/node/.codex/deepseek-model-catalog.json && echo ok"])
    check("config.toml model catalog", code == 0 and "ok" in out)

    code, out, _ = run(["docker", "exec", c, "bash", "-lc", "test -d /home/node/.codex/skills/lingxiao-identity -o -d /home/node/.codex/skills/github && echo ok"])
    check("skills mount", code == 0 and "ok" in out)

    code, out, _ = run(["docker", "exec", c, "bash", "-lc", "test -w /home/node/.codex/skills && echo ok"])
    check("skills writable", code == 0 and "ok" in out)

    web_port = 9240 if "lingxiao" in c else 9241
    ttyd_port = 9250 if "lingxiao" in c else 9251
    code, out, _ = run(["curl", "-sf", f"http://127.0.0.1:{web_port}/"], timeout=15)
    check(f"codex ui :{web_port}", code == 0 and "html" in (out or "").lower())
    code, out, _ = run(["curl", "-sf", f"http://127.0.0.1:{ttyd_port}/"], timeout=15)
    check(f"ttyd backup :{ttyd_port}", code == 0 and len(out or "") > 0)

    prompt = "Reply with exactly: CODEX_OK"
    inner = textwrap.dedent(
        f"""codex exec --json --ephemeral --skip-git-repo-check --cd /mailbus/store \\
          -s workspace-write -c 'approval_policy="never"' \\
          -m deepseek-v4-flash '{prompt}'"""
    )
    code, out, err = run(
        ["docker", "exec", c, "bash", "-lc", inner],
        timeout=args.timeout,
    )
    combined = (out or "") + (err or "")
    check("codex exec deepseek", code == 0 and "CODEX_OK" in combined, combined[-200:].replace("\n", " "))

    print(f"== done ({fails} failures) ==")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
