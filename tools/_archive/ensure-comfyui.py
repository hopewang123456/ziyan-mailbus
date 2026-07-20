#!/usr/bin/env python3
"""ComfyUI 运维 — 检测/启动/下载模型/冒烟生图。

  python tools/ensure-comfyui.py --data-dir store
  python tools/ensure-comfyui.py --start
  python tools/ensure-comfyui.py --smoke
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_WORKSPACE = os.environ.get("COMFYUI_WORKSPACE") or os.path.join(
    os.path.dirname(ROOT), "ComfyUI-win"
)
DEFAULT_PORT = int(os.environ.get("COMFYUI_PORT") or "8188")
DEFAULT_CKPT_URL = (
    "https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive/"
    "resolve/main/v1-5-pruned-emaonly.safetensors"
)
DEFAULT_CKPT_NAME = "v1-5-pruned-emaonly.safetensors"


def _venv_python(workspace: str) -> str:
    win = os.path.join(workspace, ".venv", "Scripts", "python.exe")
    if os.path.isfile(win):
        return win
    nix = os.path.join(workspace, ".venv", "bin", "python")
    if os.path.isfile(nix):
        return nix
    return sys.executable


def _base_url(port: int) -> str:
    host = os.environ.get("COMFYUI_HOST") or "127.0.0.1"
    return f"http://{host}:{port}"


def ensure_checkpoint(workspace: str, *, force: bool = False) -> str:
    ckpt_dir = os.path.join(workspace, "models", "checkpoints")
    os.makedirs(ckpt_dir, exist_ok=True)
    path = os.path.join(ckpt_dir, DEFAULT_CKPT_NAME)
    if os.path.isfile(path) and os.path.getsize(path) > 1_000_000 and not force:
        return path
    url = os.environ.get("COMFYUI_CKPT_URL") or DEFAULT_CKPT_URL
    print(f"[comfy] downloading {DEFAULT_CKPT_NAME} …")
    tmp = path + ".part"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, path)
    print(f"[comfy] checkpoint ready: {path}")
    return path


def is_running(port: int) -> bool:
    from lib.comfyui.client import health_check
    ok, _ = health_check(_base_url(port))
    return ok


def start_server(workspace: str, port: int) -> subprocess.Popen | None:
    if is_running(port):
        print(f"[comfy] already running on :{port}")
        return None
    main_py = os.path.join(workspace, "main.py")
    if not os.path.isfile(main_py):
        print(f"[comfy] missing {main_py}; run install first")
        return None
    py = _venv_python(workspace)
    log_dir = os.path.join(workspace, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "comfyui-server.log")
    env = os.environ.copy()
    env.setdefault("COMFYUI_CHECKPOINT", DEFAULT_CKPT_NAME)
    cmd = [py, main_py, "--port", str(port), "--listen", "127.0.0.1"]
    if os.environ.get("COMFYUI_CPU", "").lower() in ("1", "true", "yes"):
        cmd.append("--cpu")
    print(f"[comfy] starting: {' '.join(cmd)}")
    with open(log_path, "a", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            cmd,
            cwd=workspace,
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    for _ in range(60):
        if is_running(port):
            print(f"[comfy] server up http://127.0.0.1:{port}")
            return proc
        time.sleep(2)
    print(f"[comfy] server not ready; see {log_path}")
    return proc


def smoke_test(port: int) -> int:
    from lib.comfyui.client import generate_txt2img

    os.environ.setdefault("COMFYUI_CHECKPOINT", DEFAULT_CKPT_NAME)
    out = generate_txt2img(
        {"prompt": "mailbus smoke test, simple icon, flat vector", "steps": 12, "width": 512, "height": 512},
        base_url=_base_url(port),
        timeout=180,
    )
    print(out)
    return 0 if out.get("ok") else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="ensure ComfyUI")
    ap.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--start", action="store_true")
    ap.add_argument("--download-model", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    if args.download_model or args.start or args.smoke:
        ensure_checkpoint(args.workspace)

    if args.start or args.smoke:
        start_server(args.workspace, args.port)

    if args.smoke:
        return smoke_test(args.port)

    ok = is_running(args.port)
    print({"running": ok, "workspace": args.workspace, "port": args.port})
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
