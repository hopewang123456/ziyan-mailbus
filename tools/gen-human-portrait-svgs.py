#!/usr/bin/env python3
"""生成动漫真人风 bust 肖像 SVG（替代机器人头像）。"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "store", "agents", "json", "profile-cards.json")
OUT = os.path.join(ROOT, "docs", "avatars")

# 肤色 / 发色 / 瞳色 按 agent 微调
STYLE = {
    "lingzhao": ("#f5d0c5", "#1a1a2e", "#00d4ff"),
    "lingjin": ("#ffe4d6", "#2d1b4e", "#8b5cf6"),
    "lingxi": ("#ffd6e8", "#1e3a5f", "#22d3ee"),
    "lingtuo": ("#e8c4a0", "#0f172a", "#06b6d4"),
    "lingjian": ("#f0dcc8", "#374151", "#a78bfa"),
    "lingyan": ("#ffe0ec", "#4a1942", "#34d399"),
    "lingxun": ("#d4a574", "#1c1917", "#f472b6"),
    "lingxiao": ("#f5c99a", "#1e293b", "#3b82f6"),
    "dali": ("#e8b896", "#292524", "#ef4444"),
    "xiaoqi": ("#ffc9d9", "#831843", "#10b981"),
    "yige": ("#deb887", "#1e1b4b", "#f59e0b"),
    "lingzhang": ("#f5d6e0", "#4c0519", "#ec4899"),
}


def bust_svg(aid: str, name: str, gender: str, accent: str) -> str:
    skin, hair, eye = STYLE.get(aid, ("#f5d0c5", "#1a1a2e", accent))
    is_f = gender.startswith("女")
    hair_len = 95 if is_f else 55
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 400">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="{accent}" stop-opacity="0.35"/><stop offset="100%" stop-color="#0f172a"/></linearGradient>
  <radialGradient id="face" cx="50%" cy="40%" r="50%"><stop offset="0%" stop-color="{skin}"/><stop offset="100%" stop-color="{skin}dd"/></radialGradient>
</defs>
<rect width="320" height="400" fill="url(#bg)"/>
<ellipse cx="160" cy="380" rx="120" ry="40" fill="#000" opacity="0.25"/>
<!-- 肩 / 衣领 -->
<path d="M60 280 Q160 240 260 280 L280 400 L40 400 Z" fill="#1e293b" stroke="{accent}" stroke-width="1.2" opacity="0.9"/>
<path d="M110 280 L160 320 L210 280" fill="none" stroke="{accent}" stroke-width="1" opacity="0.5"/>
<!-- 颈 -->
<rect x="140" y="210" width="40" height="45" rx="8" fill="{skin}"/>
<!-- 脸 -->
<ellipse cx="160" cy="165" rx="72" ry="82" fill="url(#face)"/>
<!-- 发 -->
<ellipse cx="160" cy="115" rx="78" ry="{hair_len}" fill="{hair}"/>
<path d="M88 150 Q160 60 232 150 L220 200 Q160 130 100 200 Z" fill="{hair}"/>
<!-- 眼 -->
<ellipse cx="132" cy="168" rx="14" ry="10" fill="#fff"/>
<ellipse cx="188" cy="168" rx="14" ry="10" fill="#fff"/>
<circle cx="134" cy="170" r="6" fill="{eye}"/>
<circle cx="190" cy="170" r="6" fill="{eye}"/>
<circle cx="136" cy="168" r="2" fill="#fff"/>
<circle cx="192" cy="168" r="2" fill="#fff"/>
<!-- 眉 -->
<path d="M118 148 Q132 142 146 148" stroke="{hair}" stroke-width="2.5" fill="none" stroke-linecap="round"/>
<path d="M174 148 Q188 142 202 148" stroke="{hair}" stroke-width="2.5" fill="none" stroke-linecap="round"/>
<!-- 鼻嘴 -->
<path d="M160 178 L160 192" stroke="#c4a484" stroke-width="1.5" stroke-linecap="round"/>
<path d="M148 200 Q160 208 172 200" stroke="#d4848a" stroke-width="2" fill="none" stroke-linecap="round"/>
<!-- 标签 -->
<text x="160" y="365" text-anchor="middle" fill="#e2e8f0" font-size="18" font-family="Segoe UI,sans-serif" font-weight="600">{name}</text>
</svg>'''


def main():
    cards = json.load(open(CARDS, encoding="utf-8"))["cards"]
    os.makedirs(OUT, exist_ok=True)
    accents = {k: v[2] for k, v in STYLE.items()}
    for aid, c in cards.items():
        acc = accents.get(aid, "#38bdf8")
        svg = bust_svg(aid, c["name"], c.get("gender", "男"), acc)
        for suffix in ("portrait", "animated"):
            p = os.path.join(OUT, f"{aid}_{suffix}.svg")
            open(p, "w", encoding="utf-8").write(svg)
    print(f"generated {len(cards)} portrait+animated svgs")


if __name__ == "__main__":
    main()
