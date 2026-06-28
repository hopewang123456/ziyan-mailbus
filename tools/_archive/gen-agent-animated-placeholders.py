#!/usr/bin/env python3
"""生成 agent 卡片动图占位 SVG（ComfyUI 肖像就绪前使用）。"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cards = json.load(open(os.path.join(ROOT, "store", "agents", "json", "profile-cards.json"), encoding="utf-8"))["cards"]
out = os.path.join(ROOT, "docs", "avatars")
for aid, c in cards.items():
    name = c.get("name", aid)
    is_f = str(c.get("gender", "")).startswith("女")
    color = "#f472b6" if is_f else "#38bdf8"
    role = (c.get("role") or "")[:16]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 480">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.4"/>'
        f'<stop offset="100%" stop-color="#0f172a"/></linearGradient></defs>'
        f'<rect width="400" height="480" fill="url(#g)"/>'
        f'<ellipse cx="200" cy="175" rx="85" ry="95" fill="{color}" opacity="0.2"/>'
        f'<text x="200" y="340" text-anchor="middle" fill="#e2e8f0" font-size="32" font-family="sans-serif">{name}</text>'
        f'<text x="200" y="380" text-anchor="middle" fill="#94a3b8" font-size="14" font-family="sans-serif">{role}</text>'
        f"</svg>"
    )
    with open(os.path.join(out, f"{aid}_animated.svg"), "w", encoding="utf-8") as f:
        f.write(svg)
print(f"wrote {len(cards)} animated placeholders")
