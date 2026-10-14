#!/usr/bin/env python3
"""Hermes 对话探针 (DeepSeek) — 容器内 hermes chat 最小探针 + API key / 配置检查。"""
import argparse, os, subprocess, sys

HERMES_CONTAINER = "docker-agents-hermes-1"

def cmd(cmdline: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmdline, shell=True, capture_output=True, text=True, timeout=60)

def main():
    ap = argparse.ArgumentParser(description="Hermes chat probe")
    ap.add_argument("--profile", default="agent-a", help="hermes profile")
    ap.add_argument("--message", default="hi", help="test message")
    args = ap.parse_args()

    # 检查 DEEPSEEK_API_KEY
    r = cmd(f"docker exec {HERMES_CONTAINER} cat /run/hermes/.env 2>/dev/null")
    if "DEEPSEEK_API_KEY" in r.stdout:
        print("DEEPSEEK_API_KEY: SET")
    elif "OPENAI_API_KEY" in r.stdout:
        print("OPENAI_API_KEY: SET (will use gateway)")
    else:
        print("API KEY: NOT FOUND — 请通过 gateway 或 DEEPSEEK_API_KEY 设置")
        return 1

    # HERMES_DATA
    r = cmd(f"docker exec {HERMES_CONTAINER} ls /hermes-data/.hermes/profiles/ 2>/dev/null")
    if r.returncode == 0:
        print("HERMES_DATA: OK")
    else:
        print("HERMES_DATA: not mounted or missing :: profiles")
        return 1

    # .sync
    r = cmd(f"docker exec {HERMES_CONTAINER} ls /hermes-data/.hermes/profiles/{args.profile}/.sync 2>/dev/null")
    if r.returncode == 0:
        print(".sync: EXISTS")
    else:
        print(f".sync: MISSING for profile {args.profile}")

    # config.yaml
    r = cmd(f"docker exec {HERMES_CONTAINER} cat /hermes-data/.hermes/config.yaml 2>/dev/null")
    print(f"config.yaml: {r.stdout.strip()[:300] if r.stdout.strip() else 'EMPTY or MISSING'}")

    # Smoke chat
    print(f"\nSmoke chat (profile={args.profile}, msg='{args.message}')...")
    r = cmd(f"docker exec {HERMES_CONTAINER} hermes chat -p {args.profile} -m '{args.message}' 2>&1")
    if r.returncode == 0:
        print(f"  OK: {r.stdout.strip()[:500]}")
        return 0
    else:
        print(f"  FAIL: {r.stderr.strip()[:500]}")
        return 1

if __name__ == "__main__":
    exit(main())
