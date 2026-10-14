#!/usr/bin/env python3
"""修复 Cline 鉴权（codex 容器）— 同步 Hermes API key、重建 codex-web 容器、cline auth。"""
import argparse, os, subprocess, sys

def cmd(cmdline: str, check: bool = True) -> subprocess.CompletedProcess:
    print(f"[CMD] {cmdline}")
    r = subprocess.run(cmdline, shell=True, capture_output=True, text=True, timeout=300)
    if r.returncode != 0 and check:
        print(f"  WARN: rc={r.returncode}  {r.stderr.strip()[-200:]}")
    return r

def main():
    ap = argparse.ArgumentParser(description="Fix Cline auth for codex-web")
    ap.add_argument("--all", action="store_true", help="full repair")
    ap.add_argument("--sync-env", action="store_true", help="sync .env only")
    ap.add_argument("--smoke-only", action="store_true", help="smoke test only")
    args = ap.parse_args()

    if args.all or args.sync_env:
        print("=== Sync Hermes .env API key ===")
        hermes_data = os.environ.get("HERMES_DATA") or os.path.expanduser("~/.hermes")
        src = os.path.join(hermes_data, ".env")
        if not os.path.exists(src):
            print(f"ERROR: {src} not found")
            return 1
        print(f"  Source: {src}")
        # 复制 key 到 codex-web 容器环境
        with open(src) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY=") or line.startswith("OPENAI_API_KEY=") or line.startswith("HERMES_API_KEY="):
                    print(f"  Found: {line[:60]}...")

    if args.all:
        print("\n=== Rebuild codex-web container ===")
        cmd("docker compose -f docker-agents/docker-compose.yml up -d --build codex-web", check=False)

    if args.smoke_only:
        print("\n=== Smoke test ===")
        r = cmd("docker exec docker-agents-codex-web-1 which codex", check=False)
        if r.returncode == 0:
            print("  codex binary: OK")
        else:
            print("  codex binary: MISSING")
        r = cmd("docker logs docker-agents-codex-web-1 --tail 10", check=False)

    return 0

if __name__ == "__main__":
    exit(main())
