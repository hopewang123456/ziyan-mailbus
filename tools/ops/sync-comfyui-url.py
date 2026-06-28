#!/usr/bin/env python3
"""探测 ComfyUI 可达地址并写入 .env / docker-agents/.env。"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.comfyui.url_resolve import find_working_comfyui_base_url  # noqa: E402


def _set_env_key(path: str, key: str, value: str) -> bool:
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    pat = re.compile(rf"^\s*{re.escape(key)}=")
    found = False
    out: list[str] = []
    for line in lines:
        if pat.match(line):
            found = True
            out.append(f"{key}={value}\n")
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    url = find_working_comfyui_base_url()
    if not url:
        if not args.quiet:
            print("[sync-comfyui] ComfyUI unreachable. Start: wsl bash docker-agents/start-comfyui-gpu.sh")
        return 1

    for rel in (".env", os.path.join("docker-agents", ".env")):
        path = os.path.join(ROOT, rel)
        if _set_env_key(path, "COMFYUI_BASE_URL", url) and not args.quiet:
            print(f"[sync-comfyui] {rel} -> COMFYUI_BASE_URL={url}")

    if not args.quiet and "127.0.0.1" not in url:
        print("Note: WSL IP may change after reboot. Re-run this script or use .wslconfig mirrored networking.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
