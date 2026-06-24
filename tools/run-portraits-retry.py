#!/usr/bin/env python3
"""逐个生成缺失 portrait + 眨眼，ComfyUI 失败则重启。"""
import importlib.util
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
spec = importlib.util.spec_from_file_location("gap", os.path.join(ROOT, "tools", "gen-agent-portraits.py"))
gap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gap)

MISSING = ["lingxi", "lingtuo", "lingyan", "lingxun", "lingxiao", "dali", "yige", "lingzhang"]
LOG = os.path.join(ROOT, "store", "logs", "portraits-retry.log")


def log(msg: str) -> None:
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def comfy_restart() -> bool:
    subprocess.run(
        ["wsl", "bash", "-lc", "cd /mnt/e/ai_tools/mail/docker-agents && bash start-comfyui-gpu.sh"],
        cwd=ROOT, check=False,
    )
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sync-comfyui-url.py")], cwd=ROOT, check=False)
    from lib.comfyui.url_resolve import find_working_comfyui_base_url, resolve_comfyui_base_url
    resolve_comfyui_base_url.cache_clear()
    url = find_working_comfyui_base_url(retries=30, pause=6.0)
    if url:
        os.environ["COMFYUI_BASE_URL"] = url
        log(f"ComfyUI ready: {url}")
    return bool(url)


def main() -> int:
    cards = gap._load_cards()
    data_dir = os.path.join(ROOT, "store")
    ok = 0
    log("=== retry missing portraits ===")
    if not comfy_restart():
        log("ComfyUI failed to start")
        return 1
    for aid in MISSING:
        portrait = os.path.join(gap.DOCS_AVATARS, f"{aid}_portrait.png")
        animated = os.path.join(gap.DOCS_AVATARS, f"{aid}_animated.webp")
        if os.path.isfile(portrait) and os.path.getsize(portrait) > 20000 and os.path.isfile(animated):
            log(f"[{aid}] already done")
            ok += 1
            continue
        card = cards.get(aid)
        if not card:
            continue
        log(f"======== {aid} ========")
        for attempt in range(3):
            if gap.generate_one(data_dir, aid, card, force=True):
                ok += 1
                log(f"[{aid}] OK")
                break
            log(f"[{aid}] attempt {attempt+1} failed, restart ComfyUI")
            comfy_restart()
            time.sleep(10)
        else:
            log(f"[{aid}] FAIL after 3 attempts")
        time.sleep(20)
    log(f"=== retry done {ok}/{len(MISSING)} ===")
    return 0 if ok == len(MISSING) else 1


if __name__ == "__main__":
    raise SystemExit(main())
