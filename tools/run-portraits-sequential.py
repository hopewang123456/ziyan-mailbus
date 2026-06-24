#!/usr/bin/env python3
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

TODO = ["lingtuo", "lingyan", "lingxun", "lingxiao", "dali", "yige", "lingzhang"]
LOG = os.path.join(ROOT, "store", "logs", "portraits-sequential.log")


def log(m):
    print(m, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(m + "\n")


def start_comfy():
    subprocess.run(["wsl", "bash", "-lc", "cd /mnt/e/ai_tools/mail/docker-agents && bash start-comfyui-gpu.sh"], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sync-comfyui-url.py")], cwd=ROOT)
    from lib.comfyui.url_resolve import find_working_comfyui_base_url, resolve_comfyui_base_url
    resolve_comfyui_base_url.cache_clear()
    url = find_working_comfyui_base_url(retries=30, pause=5.0)
    if url:
        os.environ["COMFYUI_BASE_URL"] = url
    return url


def main():
    cards = gap._load_cards()
    data = os.path.join(ROOT, "store")
    log("=== sequential start ===")
    ok = 0
    for aid in TODO:
        p = os.path.join(gap.DOCS_AVATARS, f"{aid}_portrait.png")
        w = os.path.join(gap.DOCS_AVATARS, f"{aid}_animated.webp")
        if os.path.isfile(p) and os.path.getsize(p) > 20000 and os.path.isfile(w):
            log(f"[{aid}] skip exists")
            ok += 1
            continue
        log(f"--- {aid} ---")
        url = start_comfy()
        if not url:
            log(f"[{aid}] no ComfyUI")
            continue
        time.sleep(15)
        if gap.generate_one(data, aid, cards[aid], force=True):
            ok += 1
            log(f"[{aid}] OK")
        else:
            log(f"[{aid}] FAIL")
        time.sleep(25)
    log(f"=== sequential done {ok}/{len(TODO)} ===")


if __name__ == "__main__":
    main()
