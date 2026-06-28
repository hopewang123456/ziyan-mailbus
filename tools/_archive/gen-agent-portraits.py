#!/usr/bin/env python3
"""ComfyUI 批量生成 3D 真人风 agent 肖像 + 人物微动 WebP（眨眼，非整图动）。

肖像原则（生成时必须遵守）：
- 长相符合人物年龄、性别、性格/MBTI，俊男美女，有辨识度
- 拒绝班味儿：不要西装领带、工牌、办公室背景、证件照式僵笑

  python tools/gen-agent-portraits.py lingzhao -f
  python tools/gen-agent-portraits.py lingzhao --motion-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DOCS_AVATARS = os.path.join(ROOT, "docs", "avatars")

PORTRAIT_CORE = (
    "masterpiece, best quality, ultra photorealistic, 3D CGI render, Unreal Engine 5 MetaHuman, "
    "East Asian {beauty}, age {age}, {age_look}, "
    "{expression}, {vibe}, {outfit}, "
    "perfect facial anatomy, detailed skin pores, subsurface scattering, "
    "soft cinematic rim light, shallow depth of field, upper body portrait, looking at camera, "
    "natural charisma, attractive distinctive face, 8k uhd, octane render"
)

NEG = (
    "lowres, worst quality, bad anatomy, bad hands, extra fingers, deformed, blurry, ugly, plain, "
    "watermark, text, logo, cartoon, flat 2d, chibi, duplicate, robot, android, "
    "oversaturated, jpeg artifacts, cross-eyed, head turn, camera move, zoom, pan, "
    "business suit, necktie, formal office wear, white collar, corporate ID photo, passport photo, "
    "office background, cubicle, fluorescent lighting, stiff smile, bureaucrat, middle-aged uncle vibe, "
    "boring office worker, stock photo model, greasy hair, heavy makeup"
)

MOTION_NEG = (
    NEG
    + ", different person, identity change, pose change, background change, "
    "lighting change, relighting, shadow shift, brightness change, color grade change, "
    "rim light change, highlight movement, only lighting different, head turn"
)

# 眨眼序列：(closure 0=睁眼 1=全闭, 帧时长 ms) — 程序化眼睑合成，保证可见眨眼
BLINK_CLOSURES: tuple[tuple[float, int], ...] = (
    (0.0, 520),
    (0.42, 55),
    (1.0, 45),
    (1.0, 40),
    (0.42, 55),
    (0.0, 520),
)

MBTI_VISUAL: dict[str, str] = {
    "ENTJ": "confident sharp gaze, quiet charisma, mature leader presence without arrogance",
    "ENTP": "bright curious eyes, playful intelligent smirk, creative rebel energy",
    "INTJ": "cool reserved elegance, penetrating calm eyes, understated intensity",
    "INTP": "detached intellectual beauty, thoughtful distant gaze, subtle cool charm",
    "ISTJ": "clean classic features, steady reliable aura, composed not stiff",
    "ISFJ": "gentle warm presence, soft attentive eyes, approachable grace",
    "ESTJ": "decisive strong features, direct honest gaze, energetic not bureaucratic",
    "ESFJ": "warm radiant smile, lively friendly eyes, socially magnetic charm",
    "INFJ": "deep soulful eyes, gentle mysterious allure, quiet empathy in expression",
    "INFP": "dreamy soft features, sensitive artistic aura, tender introspective gaze",
    "ENFP": "sparkling expressive eyes, infectious enthusiasm, free-spirited charm",
    "ENFJ": "inspiring warm charisma, encouraging gentle smile, natural mentor aura",
}

# 年龄 → 外貌阶段
def _age_look(age_num: int, is_female: bool) -> str:
    if age_num <= 26:
        return "youthful fresh skin, trendy Gen-Z vibe, lively young adult"
    if age_num <= 32:
        return "refined young adult, polished but relaxed, prime attractive age"
    if age_num <= 38:
        return "mature attractive features, subtle lines of experience, distinguished charm"
    return "elegant mature beauty, graceful aging, charismatic presence"


def _parse_age(card: dict) -> int:
    raw = str(card.get("age") or "28")
    digits = "".join(c for c in raw if c.isdigit())
    try:
        return max(18, min(int(digits or 28), 55))
    except ValueError:
        return 28


def _trait_keywords(card: dict) -> str:
    """从性格/特质提炼视觉关键词。"""
    blob = " ".join([
        card.get("personality") or "",
        " ".join(card.get("traits") or []),
        card.get("motto") or "",
    ])
    hints: list[str] = []
    rules = [
        (("冷脸", "严肃"), "cool exterior with hint of warmth in eyes"),
        (("暖", "温柔", "亲和"), "warm gentle expression"),
        (("活泼", "兴奋", "分享"), "bright energetic expression"),
        (("沉默", "寡言", "隐士"), "quiet introspective calm face"),
        (("外柔内刚",), "soft appearance with determined eyes"),
        (("探索", "射手", "前沿"), "adventurous spark in eyes"),
        (("白羊", "行动"), "bold confident energy"),
        (("天蝎", "敏感"), "intense perceptive gaze"),
        (("巨蟹", "共情"), "soft empathetic eyes"),
        (("双子", "多线程"), "quick-witted lively expression"),
        (("摩羯", "务实"), "grounded mature composure, not stern boss"),
        (("水瓶", "独特"), "unique unconventional cool style"),
        (("处女", "细节"), "precise neat appearance, sharp observant eyes"),
    ]
    for keys, hint in rules:
        if any(k in blob for k in keys):
            hints.append(hint)
    return ", ".join(dict.fromkeys(hints)) if hints else "natural authentic personality showing in face"


def _outfit_for(card: dict, is_female: bool) -> str:
    """穿搭：有风格感，禁止班味正装。"""
    role = (card.get("role") or "").lower()
    fw = (card.get("framework") or "").lower()
    if is_female:
        base = "stylish casual chic, designer knit or elegant off-shoulder top, subtle jewelry"
    else:
        base = "smart casual layers, premium henley or minimalist jacket, no tie no suit"
    if any(k in role for k in ("网安", "安全", "渗透", "审查", "测试", "巡检")):
        return base + ", dark muted tones, tech-creative aesthetic, hoodie or tactical casual"
    if any(k in role for k in ("编码", "dev", "架构", "技术")):
        return base + ", tech creator aesthetic, relaxed developer style"
    if any(k in role for k in ("运营", "内容", "方案")):
        return base + ", creative industry casual, editorial photoshoot vibe"
    if any(k in role for k in ("调度", "神经中枢")):
        return base + ", youthful trendy street-smart casual"
    if any(k in role for k in ("账", "商务", "回款")):
        return base + ", refined minimalist fashion, accountant chic not office clerk"
    if "openclaw" in fw or "cline" in fw:
        return base + ", modern creative workspace casual"
    return base + ", lifestyle portrait styling, magazine cover quality"


def build_portrait_prompt(card: dict) -> str:
    """按 profile-card 生成肖像 prompt。"""
    is_female = str(card.get("gender", "")).startswith("女")
    age_num = _parse_age(card)
    mbti = (card.get("mbti") or "").upper().strip()
    beauty = "stunning beautiful woman, gorgeous feminine features" if is_female else "handsome man, sharp attractive masculine features"
    expression = MBTI_VISUAL.get(mbti, "natural confident expression matching personality")
    trait_hint = _trait_keywords(card)
    if trait_hint:
        expression = f"{expression}, {trait_hint}"
    role = (card.get("role") or "")[:60]
    vibe = f"character vibe inspired by role: {role}" if role else "unique memorable presence"
    return PORTRAIT_CORE.format(
        beauty=beauty,
        age=age_num,
        age_look=_age_look(age_num, is_female),
        expression=expression,
        vibe=vibe,
        outfit=_outfit_for(card, is_female),
    )


def _load_cards() -> dict:
    path = os.path.join(ROOT, "store", "agents", "json", "profile-cards.json")
    if not os.path.isfile(path):
        import subprocess
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sync-profile-cards.py")], check=False)
    return json.load(open(path, encoding="utf-8")).get("cards") or {}


def _download(url: str, dest: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mailbus-portrait/2.0"})
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
        with open(dest, "wb") as f:
            f.write(data)
        return len(data) > 8000
    except Exception as exc:
        print(f"  download fail: {exc}")
        return False


def _comfy_txt2img(data_dir: str, prompt: str, *, seed: int, w: int = 576, h: int = 768, steps: int = 28) -> dict:
    from lib.comfyui.client import generate_txt2img
    from lib.comfyui.url_resolve import resolve_comfyui_base_url

    resolve_comfyui_base_url.cache_clear()
    return generate_txt2img(
        {
            "prompt": prompt,
            "negative": NEG,
            "width": w,
            "height": h,
            "steps": steps,
            "cfg": 7.5,
            "seed": seed,
        },
        timeout=420,
    )


def _wait_comfyui(*, retries: int = 12, pause: float = 5.0) -> bool:
    from lib.comfyui.url_resolve import find_working_comfyui_base_url, resolve_comfyui_base_url

    for _ in range(retries):
        resolve_comfyui_base_url.cache_clear()
        url = find_working_comfyui_base_url(retries=1, pause=1.0)
        if url:
            os.environ["COMFYUI_BASE_URL"] = url
            return True
        time.sleep(pause)
    return False


def _sample_skin_tone(im) -> tuple[int, int, int]:
    w, h = im.size
    patch = im.crop((int(w * 0.10), int(h * 0.30), int(w * 0.24), int(h * 0.44)))
    pixels = list(patch.getdata())
    if not pixels:
        return (185, 155, 135)
    return (
        sum(p[0] for p in pixels) // len(pixels),
        sum(p[1] for p in pixels) // len(pixels),
        sum(p[2] for p in pixels) // len(pixels),
    )


def _detect_eye_centers(im) -> list[tuple[int, int]]:
    """从肖像暗部自动定位双眼中心。"""
    from PIL import ImageOps

    w, h = im.size
    gray = ImageOps.grayscale(im)
    y0, y1 = int(h * 0.14), int(h * 0.40)
    x0, x1 = int(w * 0.22), int(w * 0.78)
    best_y, best_score = int(h * 0.28), 0
    for y in range(y0, y1):
        score = sum(255 - gray.getpixel((x, y)) for x in range(x0, x1, 2))
        if score > best_score:
            best_score = score
            best_y = y
    cy = best_y
    dark: list[tuple[int, int]] = []
    for x in range(x0, x1):
        d = 255 - gray.getpixel((x, cy))
        if d > 70:
            dark.append((x, d))
    dark.sort(key=lambda t: t[1], reverse=True)
    if len(dark) < 2:
        return [(int(w * 0.44), cy), (int(w * 0.56), cy)]
    mid = w // 2
    left = [x for x, _ in dark if x < mid][:12]
    right = [x for x, _ in dark if x >= mid][:12]
    centers: list[tuple[int, int]] = []
    if left:
        centers.append((sum(left) // len(left), cy))
    if right:
        centers.append((sum(right) // len(right), cy))
    if len(centers) == 1:
        centers.append((int(w * 0.56), cy) if centers[0][0] < mid else (int(w * 0.44), cy))
    return sorted(centers, key=lambda t: t[0])[:2]


def _synthesize_blink_frame(portrait_path: str, out_path: str, closure: float) -> bool:
    """在肖像上合成眼睑闭合 — 只动眼皮，不换脸不改光影。"""
    if closure <= 0.01:
        return _copy_frame(portrait_path, out_path)
    try:
        from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    except ImportError:
        return False
    base = Image.open(portrait_path).convert("RGB")
    w, h = base.size
    skin = _sample_skin_tone(base)
    shadow = tuple(max(0, c - 45) for c in skin)
    lid = tuple(min(255, int(c * 0.98)) for c in skin)
    out = base.copy()
    rx = max(10, int(w * 0.062))
    ry = max(5, int(h * 0.032))
    for cx, cy in _detect_eye_centers(base):
        x0, y0 = max(0, cx - rx), max(0, cy - ry)
        x1, y1 = min(w, cx + rx), min(h, cy + ry)
        patch = out.crop((x0, y0, x1, y1))
        pw, ph = patch.size
        emask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(emask).ellipse((0, 0, pw - 1, ph - 1), fill=255)
        emask = emask.filter(ImageFilter.GaussianBlur(radius=max(1, int(w * 0.003))))
        if closure >= 0.92:
            closed = ImageEnhance.Brightness(patch).enhance(0.55)
            closed = ImageEnhance.Contrast(closed).enhance(0.85)
            closed = closed.filter(ImageFilter.GaussianBlur(radius=max(1, int(w * 0.004))))
            layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            d.ellipse((0, 0, pw, ph), fill=(*lid, 200))
            d.arc((0, int(ph * 0.15), pw, ph), 200, 340, fill=(*shadow, 220), width=max(2, int(h * 0.006)))
            closed = Image.alpha_composite(closed.convert("RGBA"), layer).convert("RGB")
            out.paste(closed, (x0, y0), emask)
        else:
            lid_h = max(2, int(ph * closure))
            layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            d.rectangle((0, 0, pw, lid_h), fill=(*lid, 215))
            d.line([(0, lid_h), (pw, lid_h)], fill=(*shadow, 200), width=max(2, int(h * 0.004)))
            top = patch.crop((0, 0, pw, min(ph, lid_h + 2)))
            blended = Image.alpha_composite(top.convert("RGBA"), layer.crop((0, 0, pw, min(ph, lid_h + 2)))).convert("RGB")
            partial_mask = emask.crop((0, 0, pw, min(ph, lid_h + 2)))
            out.paste(blended, (x0, y0), partial_mask)
    try:
        out.save(out_path, format="PNG")
        return os.path.isfile(out_path) and os.path.getsize(out_path) > 10000
    except OSError:
        return False


def _copy_frame(src: str, dest: str) -> bool:
    import shutil
    try:
        shutil.copy2(src, dest)
        return os.path.isfile(dest) and os.path.getsize(dest) > 10000
    except OSError:
        return False


def _eye_region_diff(path_a: str, path_b: str) -> float:
    """眼部区域平均像素差，用于验证是否真的眨眼。"""
    try:
        from PIL import Image
    except ImportError:
        return 999.0
    i1 = Image.open(path_a).convert("L")
    i2 = Image.open(path_b).convert("L")
    w, h = i1.size
    total, count = 0.0, 0
    for cx, cy in _detect_eye_centers(i1):
        rx, ry = max(10, int(w * 0.07)), max(6, int(h * 0.04))
        box = (max(0, cx - rx), max(0, cy - ry), min(w, cx + rx), min(h, cy + ry))
        p1 = list(i1.crop(box).getdata())
        p2 = list(i2.crop(box).getdata())
        if p1:
            total += sum(abs(a - b) for a, b in zip(p1, p2)) / len(p1)
            count += 1
    return total / count if count else 0.0


def _save_webp(frames: list[str], durations: list[int], dest: str) -> bool:
    try:
        from PIL import Image
    except ImportError:
        print("  pillow missing — pip install pillow")
        return False
    imgs = [Image.open(p).convert("RGB") for p in frames if os.path.isfile(p)]
    if len(imgs) < 3:
        return False
    durs = durations[: len(imgs)]
    while len(durs) < len(imgs):
        durs.append(durs[-1] if durs else 120)
    imgs[0].save(
        dest,
        save_all=True,
        append_images=imgs[1:],
        duration=durs,
        loop=0,
        format="WEBP",
        quality=88,
    )
    return os.path.isfile(dest) and os.path.getsize(dest) > 12000


def _generate_motion_webp(
    data_dir: str,
    aid: str,
    portrait: str,
    animated: str,
    base_prompt: str,
    seed: int,
    *,
    force: bool = False,
    assemble_only: bool = False,
) -> bool:
    if not force and os.path.isfile(animated) and os.path.getsize(animated) > 12000:
        print("  skip animated (exists)")
        return True
    if not os.path.isfile(portrait) or os.path.getsize(portrait) < 20000:
        print("  motion skip: need portrait first")
        return False

    frames_dir = os.path.join(DOCS_AVATARS, "_frames", aid)
    os.makedirs(frames_dir, exist_ok=True)
    frame_paths: list[str] = []
    durations: list[int] = []
    open_anchor = os.path.join(frames_dir, "blink00.png")

    print(f"  motion: {len(BLINK_CLOSURES)} frames (eyelid synthesis blink)")
    for i, (closure, dur_ms) in enumerate(BLINK_CLOSURES):
        fp = os.path.join(frames_dir, f"blink{i:02d}.png")
        if not force and os.path.isfile(fp) and os.path.getsize(fp) > 10000:
            frame_paths.append(fp)
            durations.append(dur_ms)
            continue

        if assemble_only:
            print(f"  blink frame {i} missing, cannot assemble-only")
            break

        if _synthesize_blink_frame(portrait, fp, closure):
            frame_paths.append(fp)
            durations.append(dur_ms)
            anchor = open_anchor if os.path.isfile(open_anchor) else portrait
            diff = _eye_region_diff(anchor, fp) if closure > 0.05 else 0.0
            label = "open" if closure <= 0.01 else f"closure={closure:.0%}"
            print(f"  blink frame {i} ok ({label}, eye_diff={diff:.1f})")
        else:
            print(f"  blink frame {i} synthesize fail")
            break

    if len(frame_paths) >= 4:
        closed = [p for p in frame_paths if "blink02" in p or "blink03" in p]
        if closed and _eye_region_diff(frame_paths[0], closed[0]) < 15.0:
            print("  WARN: blink weak in eye region")

    if len(frame_paths) >= 4 and _save_webp(frame_paths, durations, animated):
        print(f"  saved motion webp {animated} ({len(frame_paths)} frames, real blink)")
        return True
    print("  motion webp NOT saved — 需要有效眨眼帧，拒绝光影变化冒充")
    return False


def generate_one(
    data_dir: str,
    aid: str,
    card: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    motion_only: bool = False,
    assemble_only: bool = False,
) -> bool:
    os.makedirs(DOCS_AVATARS, exist_ok=True)
    portrait = os.path.join(DOCS_AVATARS, f"{aid}_portrait.png")
    animated = os.path.join(DOCS_AVATARS, f"{aid}_animated.webp")

    age = _parse_age(card)
    base_prompt = build_portrait_prompt(card)
    seed = abs(hash("mailbus-portrait-v4-" + aid + "-" + str(age))) % (2**31)

    print(f"[{aid}] {card.get('name')} age={age} mbti={card.get('mbti','')} seed={seed}")
    if dry_run:
        print(f"  portrait: {base_prompt[:200]}...")
        print(f"  motion: {len(BLINK_CLOSURES)} frames (eyelid synthesis blink)")
        return True

    if assemble_only:
        motion_only = True

    if not motion_only:
        if not force and os.path.isfile(portrait) and os.path.getsize(portrait) > 20000:
            print("  skip portrait (exists)")
        else:
            r = _comfy_txt2img(data_dir, base_prompt, seed=seed, steps=22)
            if not r.get("ok"):
                print(f"  ComfyUI fail: {r.get('error')} {r.get('message', '')}")
                return False
            images = r.get("images") or []
            if not images or not _download(images[0].get("view_url", ""), portrait):
                print("  portrait download failed")
                return False
            print(f"  saved portrait {portrait}")
            time.sleep(20)

    motion_ok = _generate_motion_webp(
        data_dir,
        aid,
        portrait,
        animated,
        base_prompt,
        seed,
        force=force or motion_only,
        assemble_only=assemble_only,
    )
    return os.path.isfile(portrait) and (motion_ok or (not force and os.path.isfile(animated)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agents", nargs="*", help="agent id，默认全部")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", "-f", action="store_true")
    ap.add_argument("--motion-only", action="store_true", help="仅重生成眨眼动图（需已有 portrait.png）")
    ap.add_argument("--assemble-only", action="store_true", help="仅从已有帧合成 webp，不调用 ComfyUI")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    args = ap.parse_args()

    from lib.comfyui.url_resolve import find_working_comfyui_base_url, resolve_comfyui_base_url

    resolve_comfyui_base_url.cache_clear()
    url = find_working_comfyui_base_url()
    need_comfy = not args.dry_run and not args.assemble_only and not args.motion_only
    if not url and need_comfy:
        print("ComfyUI unreachable. Start: wsl bash docker-agents/start-comfyui-gpu.sh")
        return 1
    if url:
        os.environ["COMFYUI_BASE_URL"] = url
        print(f"ComfyUI: {url}")
    elif args.motion_only:
        print("ComfyUI: skip (motion-only eyelid synthesis)")

    cards = _load_cards()
    targets = args.agents or list(cards.keys())
    ok = sum(
        1
        for aid in targets
        if (c := cards.get(aid))
        and generate_one(
            args.data_dir,
            aid,
            c,
            force=args.force,
            dry_run=args.dry_run,
            motion_only=args.motion_only,
            assemble_only=args.assemble_only,
        )
    )
    print(f"done {ok}/{len(targets)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
