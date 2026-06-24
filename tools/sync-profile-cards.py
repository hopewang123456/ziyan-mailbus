#!/usr/bin/env python3
"""从 identities 同步 profile-cards.json（含对子言关系字段）。"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.utils import identity_candidates


def _field(text: str, key: str) -> str:
    m = re.search(rf"\*\*{re.escape(key)}\*\*[：:]\s*([^|\n]+)", text)
    if m:
        return m.group(1).strip()
    m = re.search(rf"[-*]\s+\*\*{re.escape(key)}\*\*[：:]\s*(.+)", text)
    if m:
        return m.group(1).strip()
    m = re.search(rf"^\s*[-*]\s+{re.escape(key)}[：:]\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def _field_alt(text: str, key: str) -> str:
    """lingxun 等 ## 基本信息 块。"""
    m = re.search(rf"[-*]\s+\*\*{re.escape(key)}\*\*[：:]\s*([^|\n]+)", text)
    if m:
        return m.group(1).strip()
    m = re.search(rf"\|\s*\*\*{re.escape(key)}\*\*[：:]\s*([^|\n]+)", text)
    return m.group(1).strip() if m else ""


def _read_identity(data_dir: str, aid: str) -> str:
    for p in identity_candidates(data_dir, aid, ""):
        if os.path.isfile(p):
            return open(p, encoding="utf-8", errors="replace").read()
    return ""


def _ziyan_bond(text: str) -> str:
    for pat in (
        r"-\s+\*\*对子言[^*]*\*\*[：:]\s*(.+)",
        r"-\s+\*\*与子言\*\*[：:]\s*(.+)",
        r"-\s+\*\*对子言的态度\*\*[：:]\s*(.+)",
        r"-\s+\*\*对子言的特殊感\*\*[：:]\s*(.+)",
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return ""


def _traits(text: str) -> list[str]:
    m = re.search(r"##\s*(?:核心特质|人格特质)[\s\S]*?(?=##|$)", text)
    if not m:
        return []
    out = []
    for line in m.group(0).splitlines():
        x = re.match(r"-\s+\*\*(.+?)\*\*[：:]?\s*(.*)", line.strip())
        if x:
            head, tail = x.group(1).strip(), x.group(2).strip()
            if head.startswith("对子言") or head.startswith("与子言"):
                continue
            label = head if not tail else f"{head} — {tail[:60]}"
            if not re.match(r"^(ENTJ|INTJ|INTP|ISTJ|INFJ|ENTP|ISFP)", head):
                out.append(label)
    return out[:8]


def main() -> int:
    data_dir = os.path.join(ROOT, "store")
    roster = json.load(open(os.path.join(data_dir, "roles", "json", "roster.json"), encoding="utf-8"))
    cards = {}
    for m in roster.get("members", []):
        aid = m["id"]
        text = _read_identity(data_dir, aid)
        gender = _field(text, "性别") or _field_alt(text, "性别") or ("女" if m.get("gender") == "female" else "男")
        age = _field(text, "年龄") or _field_alt(text, "年龄")
        zodiac = _field(text, "星座") or _field_alt(text, "星座")
        mbti = _field(text, "MBTI") or _field_alt(text, "MBTI")
        role = _field(text, "角色") or _field_alt(text, "角色") or m.get("domain", "")
        cards[aid] = {
            "id": aid,
            "name": m.get("display", {}).get("zh") or aid,
            "gender": gender,
            "age": age,
            "zodiac": zodiac,
            "mbti": mbti,
            "role": role,
            "motto": _field(text, "座右铭"),
            "ziyan_bond": _ziyan_bond(text),
            "personality": " · ".join(_traits(text)[:3]),
            "traits": _traits(text),
            "framework": m.get("framework", ""),
            "portrait": f"avatars/{aid}_portrait.svg",
            "animated": f"avatars/{aid}_animated.svg",
            "avatar": f"avatars/{aid}_portrait.svg",
        }
    out = os.path.join(data_dir, "agents", "json", "profile-cards.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"version": "1.0.1", "updated_at": date.today().isoformat(), "cards": cards}, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(cards)} cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
