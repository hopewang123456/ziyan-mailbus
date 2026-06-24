#!/usr/bin/env python3
"""生成 Dashboard 机器人风格 SVG 头像（唯一入口，替代旧版 generate_avatars*.py）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "avatars"

# key, display, accent
AGENTS = [
    ("ziyan", "子言", "#f59e0b"),
    ("lingzhao", "灵昭", "#00d4ff"),
    ("lingjin", "灵瑾", "#8b5cf6"),
    ("lingxi", "灵犀", "#22d3ee"),
    ("lingtuo", "灵拓", "#06b6d4"),
    ("lingzhang", "灵账", "#ec4899"),
    ("lingxun", "灵巡", "#f472b6"),
    ("lingjian", "灵鉴", "#a78bfa"),
    ("lingyan", "灵验", "#34d399"),
    ("xiaoqi", "小七", "#10b981"),
    ("yige", "一哥", "#f59e0b"),
    ("lingxiao", "灵霄", "#3b82f6"),
    ("dali", "大力", "#ef4444"),
]


def _variant(key: str) -> int:
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % 4


def robot_svg(key: str, label: str, color: str) -> str:
    v = _variant(key)
    # 眼型：圆 / 横条 / 六边形 / 双环
    eyes = [
        f'<circle cx="12" cy="17" r="2.8" fill="{color}"/><circle cx="20" cy="17" r="2.8" fill="{color}"/>',
        f'<rect x="9" y="15.5" width="6" height="3" rx="1" fill="{color}"/><rect x="17" y="15.5" width="6" height="3" rx="1" fill="{color}"/>',
        f'<polygon points="12,14 15,17 12,20 9,17" fill="{color}"/><polygon points="20,14 23,17 20,20 17,17" fill="{color}"/>',
        f'<circle cx="12" cy="17" r="3.5" fill="none" stroke="{color}" stroke-width="1.2"/><circle cx="12" cy="17" r="1.2" fill="{color}"/>'
        f'<circle cx="20" cy="17" r="3.5" fill="none" stroke="{color}" stroke-width="1.2"/><circle cx="20" cy="17" r="1.2" fill="{color}"/>',
    ][v]
    # 天线
    ant = [
        f'<line x1="16" y1="9" x2="16" y2="4" stroke="{color}" stroke-width="1.5"/><circle cx="16" cy="3" r="1.8" fill="{color}"/>',
        f'<line x1="14" y1="9" x2="11" y2="3" stroke="{color}" stroke-width="1.2"/><line x1="18" y1="9" x2="21" y2="3" stroke="{color}" stroke-width="1.2"/>',
        f'<line x1="16" y1="9" x2="16" y2="2" stroke="{color}" stroke-width="1.5"/><rect x="14" y="1" width="4" height="2" rx="1" fill="{color}"/>',
        f'<path d="M16 9 L16 5 M13 6 L16 3 L19 6" stroke="{color}" stroke-width="1.2" fill="none" stroke-linecap="round"/>',
    ][v]
    badge = f'<rect x="13" y="22" width="6" height="2" rx="1" fill="{color}" opacity="0.45"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" role="img" aria-label="{label}">
  <title>{label}</title>
  <rect width="32" height="32" rx="8" fill="#0a0a18"/>
  <rect x="6" y="9" width="20" height="19" rx="5" fill="#12122a" stroke="{color}" stroke-width="1.4" opacity="0.95"/>
  {ant}
  {eyes}
  {badge}
  <line x1="8" y1="13" x2="24" y2="13" stroke="{color}" stroke-width="0.6" opacity="0.25"/>
</svg>
'''


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for key, label, color in AGENTS:
        path = OUT / f"{key}.svg"
        path.write_text(robot_svg(key, label, color), encoding="utf-8")
        print(f"  wrote {path.name}")
    print(f"Done: {len(AGENTS)} robot avatars → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
