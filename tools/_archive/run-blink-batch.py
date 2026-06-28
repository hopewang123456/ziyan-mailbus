#!/usr/bin/env python3
"""批量：已有 portrait 则只合成眨眼；无 portrait 则调 ComfyUI 生图。"""
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
LOG = os.path.join(ROOT, "store", "logs", f"portraits-batch-{os.getpid()}.log")

spec = importlib.util.spec_from_file_location("gap", os.path.join(ROOT, "tools", "gen-agent-portraits.py"))
gap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gap)

AGENTS = [
    "lingzhao", "lingjin", "lingxi", "lingtuo", "lingjian", "lingyan",
    "lingxun", "lingxiao", "dali", "xiaoqi", "yige", "lingzhang",
]

def log(msg: str) -> None:
    line = msg.rstrip()
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def comfy_up() -> bool:
    subprocess.run(
        ["wsl", "bash", "-lc", "cd /mnt/e/ai_tools/mail/docker-agents && bash start-comfyui-gpu.sh"],
        cwd=ROOT,
        check=False,
    )
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sync-comfyui-url.py")], cwd=ROOT, check=False)
    from lib.comfyui.url_resolve import find_working_comfyui_base_url, resolve_comfyui_base_url
    resolve_comfyui_base_url.cache_clear()
    url = find_working_comfyui_base_url(retries=12, pause=5.0)
    if url:
        os.environ["COMFYUI_BASE_URL"] = url
    return bool(url)


def main() -> int:
    cards = gap._load_cards()
    data_dir = os.path.join(ROOT, "store")
    ok = 0
    log(f"=== batch eyelid blink start ===")
    for aid in AGENTS:
        card = cards.get(aid)
        if not card:
            log(f"[{aid}] skip: no profile card")
            continue
        portrait = os.path.join(gap.DOCS_AVATARS, f"{aid}_portrait.png")
        animated = os.path.join(gap.DOCS_AVATARS, f"{aid}_animated.webp")
        log(f"======== {aid} ========")
        if os.path.isfile(portrait) and os.path.getsize(portrait) > 20000:
            motion_ok = gap._generate_motion_webp(
                data_dir, aid, portrait, animated, "", 0, force=True, assemble_only=False
            )
            if motion_ok:
                ok += 1
                log(f"[{aid}] motion ok")
            else:
                log(f"[{aid}] motion FAIL")
            continue
        if not comfy_up():
            log(f"[{aid}] ComfyUI down, skip portrait")
            continue
        if gap.generate_one(data_dir, aid, card, force=True):
            ok += 1
            log(f"[{aid}] portrait+motion ok")
        else:
            log(f"[{aid}] FAIL")
            comfy_up()
    log(f"=== done {ok}/{len(AGENTS)} ===")
    return 0 if ok == len(AGENTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
