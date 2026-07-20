#!/usr/bin/env python3
"""ComfyUI GPU 冒烟 — 直连 client + mailbus invoke_tool（不启动 Windows 原生 ComfyUI）。"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 加载 .env
env_path = os.path.join(ROOT, ".env")
if os.path.isfile(env_path):
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


def wait_comfyui(base: str, attempts: int = 12) -> bool:
    from lib.comfyui.client import health_check

    for i in range(attempts):
        ok, body = health_check(base)
        if ok:
            dev = (body.get("devices") or [{}])[0]
            print(f"[wait] OK attempt={i+1} device={dev.get('name', '?')}")
            return True
        print(f"[wait] not ready attempt={i+1}")
        time.sleep(10)
    return False


def main() -> int:
    base = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    data_dir = os.path.join(ROOT, "store")
    print(f"[smoke] COMFYUI_BASE_URL={base}")

    if not wait_comfyui(base):
        print("[smoke] FAIL: ComfyUI 不可达", file=sys.stderr)
        return 1

    from lib.gpu_coordinator import acquire_gpu, load_gpu_sharing_config, release_gpu, _load_store_config

    store_cfg = _load_store_config(data_dir)
    acq = acquire_gpu("comfyui", store_cfg)
    print(f"[smoke] gpu acquire: {json.dumps({k: acq.get(k) for k in ('ok','skipped','steps')}, ensure_ascii=False)}")

    from lib.comfyui.client import generate_txt2img

    t0 = time.time()
    out = generate_txt2img(
        {
            "prompt": "mailbus smoke test, simple red circle icon, flat vector, white background",
            "steps": 12,
            "width": 512,
            "height": 512,
        },
        base_url=base,
        timeout=300,
    )
    dt = time.time() - t0
    print(f"[smoke] client generate_txt2img ({dt:.1f}s): ok={out.get('ok')}")
    if not out.get("ok"):
        print(json.dumps(out, ensure_ascii=False, indent=2))
        release_gpu("comfyui", store_cfg)
        return 1
    print(f"[smoke] images={len(out.get('images') or [])} seed={out.get('seed')}")

    from lib.external_tools import invoke_tool

    t1 = time.time()
    inv = invoke_tool(
        data_dir,
        agent_id="mailbus",
        tool_id="image-generate",
        inputs={
            "prompt": "mailbus invoke_tool smoke, blue square icon, minimal",
            "steps": 12,
            "width": 512,
            "height": 512,
        },
        dry_run=False,
    )
    dt2 = time.time() - t1
    print(f"[smoke] invoke_tool ({dt2:.1f}s): ok={inv.get('ok')}")
    if inv.get("gpu_acquire"):
        print(f"[smoke] gpu_acquire steps={len(inv['gpu_acquire'].get('steps') or [])}")
    if not inv.get("ok"):
        print(json.dumps(inv, ensure_ascii=False, indent=2))
        return 1
    print("[smoke] PASS")
    release_gpu("comfyui", store_cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
