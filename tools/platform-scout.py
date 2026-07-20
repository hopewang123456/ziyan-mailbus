#!/usr/bin/env python3
"""platform-scout — 按 leads-sources.json 抓取线索 raw 快照。

用法:
  python tools/platform-scout.py --data-dir store
  python tools/platform-scout.py --data-dir store --platform v2ex --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.utils import json_read, json_write, _now_iso

TZ_CN = timezone(timedelta(hours=8))

V2EX_JOBS_RSS = "https://www.v2ex.com/feed/jobs.xml"


def _today() -> str:
    return datetime.now(TZ_CN).strftime("%Y-%m-%d")


def _load_sources(data_dir: str) -> dict:
    path = os.path.join(data_dir, "config", "leads-sources.json")
    if not os.path.isfile(path):
        path = os.path.join(data_dir, "config", "leads-sources.example.json")
    return json_read(path, {})


def _keyword_match(text: str, include: list[str], exclude: list[str]) -> bool:
    t = (text or "").lower()
    if exclude and any(k.lower() in t for k in exclude):
        return False
    if include and not any(k.lower() in t for k in include):
        return False
    return True


def _fetch(url: str, *, user_agent: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _parse_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    tag = root.tag.rsplit("}", 1)[-1]

    if tag == "feed":
        items = []
        for entry in root.findall("atom:entry", ATOM_NS):
            title = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()
            link = ""
            for ln in entry.findall("atom:link", ATOM_NS):
                if ln.get("rel") in (None, "alternate"):
                    link = (ln.get("href") or "").strip()
                    break
            body = (
                entry.findtext("atom:content", default="", namespaces=ATOM_NS)
                or entry.findtext("atom:summary", default="", namespaces=ATOM_NS)
                or ""
            ).strip()
            pub = (entry.findtext("atom:published", default="", namespaces=ATOM_NS) or entry.findtext(
                "atom:updated", default="", namespaces=ATOM_NS
            ) or "").strip()
            ref = ""
            m = re.search(r"/t/(\d+)", link)
            if m:
                ref = m.group(1)
            items.append({
                "title": title,
                "source_url": link,
                "source_ref": ref,
                "body_text": re.sub(r"<[^>]+>", " ", body)[:2000],
                "published_at": pub,
            })
        return items

    channel = root.find("channel")
    if channel is None:
        return []
    items = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        ref = ""
        m = re.search(r"/t/(\d+)", link)
        if m:
            ref = m.group(1)
        items.append({
            "title": title,
            "source_url": link,
            "source_ref": ref,
            "body_text": re.sub(r"<[^>]+>", " ", desc)[:2000],
            "published_at": pub,
        })
    return items


def scout_v2ex(platform: dict, *, user_agent: str, max_items: int) -> list[dict]:
    include = (platform.get("filters") or {}).get("keywords_include") or []
    exclude = (platform.get("filters") or {}).get("keywords_exclude") or []
    raw = _fetch(V2EX_JOBS_RSS, user_agent=user_agent)
    out = []
    for row in _parse_feed(raw):
        blob = f"{row.get('title', '')} {row.get('body_text', '')}"
        if not _keyword_match(blob, include, exclude):
            continue
        out.append({
            "platform": "v2ex",
            "source_ref": row.get("source_ref"),
            "source_url": row.get("source_url"),
            "fetched_at": _now_iso(),
            "title": row.get("title"),
            "body_text": row.get("body_text"),
            "tags": [],
        })
        if len(out) >= max_items:
            break
    return out


def scout_github_issues(platform: dict, *, user_agent: str, max_items: int) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return []
    include = (platform.get("filters") or {}).get("keywords_include") or []
    exclude = (platform.get("filters") or {}).get("keywords_exclude") or []
    q = "help+wanted+bounty+in:title,body"
    url = f"https://api.github.com/search/issues?q={q}&sort=updated&order=desc&per_page={min(max_items, 30)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        return []
    out = []
    for item in data.get("items") or []:
        title = item.get("title") or ""
        body = (item.get("body") or "")[:2000]
        if not _keyword_match(f"{title} {body}", include, exclude):
            continue
        repo = (item.get("repository_url") or "").rsplit("/", 2)[-2:]
        ref = f"{'/'.join(repo)}#{item.get('number')}" if repo else str(item.get("number"))
        out.append({
            "platform": "github_issues",
            "source_ref": ref,
            "source_url": item.get("html_url"),
            "fetched_at": _now_iso(),
            "title": title,
            "body_text": body,
            "tags": [lbl.get("name") for lbl in (item.get("labels") or []) if isinstance(lbl, dict)],
        })
        if len(out) >= max_items:
            break
    return out


def run_scout(
    data_dir: str,
    *,
    platform_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    cfg = _load_sources(data_dir)
    defaults = cfg.get("defaults") or {}
    user_agent = defaults.get("user_agent") or "OnePersonCo-Scout/0.1"
    max_items = int(defaults.get("max_items_per_run") or 50)
    rate_limit = float(defaults.get("rate_limit_seconds") or 3)
    raw_base = (cfg.get("routing") or {}).get("raw_output_dir") or "store/leads/raw"
    if raw_base.startswith("/mailbus/"):
        raw_base = os.path.join(data_dir, "leads", "raw")
    elif not os.path.isabs(raw_base):
        raw_base = os.path.join(data_dir, raw_base.replace("store/", "").lstrip("/"))

    platforms = [p for p in (cfg.get("platforms") or []) if p.get("enabled")]
    if platform_id:
        platforms = [p for p in platforms if p.get("id") == platform_id]

    stats = {"platforms": {}, "total": 0, "dry_run": dry_run}
    for plat in platforms:
        pid = plat.get("id") or "unknown"
        mode = plat.get("scout_mode") or ""
        items: list[dict] = []
        if mode == "rss" and pid == "v2ex":
            items = scout_v2ex(plat, user_agent=user_agent, max_items=max_items)
        elif mode == "github_search" and pid == "github_issues":
            items = scout_github_issues(plat, user_agent=user_agent, max_items=max_items)
        else:
            stats["platforms"][pid] = {"skipped": True, "reason": f"unsupported mode {mode}"}
            continue

        stats["platforms"][pid] = {"count": len(items)}
        stats["total"] += len(items)
        if dry_run or not items:
            continue

        out_dir = os.path.join(raw_base, pid)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{_today()}.json")
        existing = json_read(out_path, [])
        if not isinstance(existing, list):
            existing = []
        seen = {x.get("source_ref") for x in existing if isinstance(x, dict)}
        merged = list(existing)
        new_count = 0
        for row in items:
            if row.get("source_ref") in seen:
                continue
            merged.append(row)
            seen.add(row.get("source_ref"))
            new_count += 1
        json_write(out_path, merged)
        stats["platforms"][pid]["path"] = out_path
        stats["platforms"][pid]["new"] = new_count
        time.sleep(rate_limit)

    if not dry_run:
        _notify_after_scout(data_dir, stats)
    return stats


def _notify_after_scout(data_dir: str, stats: dict) -> None:
    """按 leads-sources.routing.after_scout_notify_agent 写入 task 通知灵拓。"""
    cfg = _load_sources(data_dir)
    agent = ((cfg.get("routing") or {}).get("after_scout_notify_agent") or "").strip()
    if not agent:
        return
    new_total = sum(
        int(p.get("new") or 0)
        for p in (stats.get("platforms") or {}).values()
        if isinstance(p, dict)
    )
    if new_total <= 0:
        return
    lines = [f"📡 platform-scout 新线索 {new_total} 条，请研判并更新 store/leads/order-intake.json"]
    for pid, p in (stats.get("platforms") or {}).items():
        if not isinstance(p, dict):
            continue
        n = int(p.get("new") or 0)
        if n:
            lines.append(f"  · {pid}: +{n} → {p.get('path', '(raw)')}")
    lines.append("参考: store/rules/order-intake.schema.json · 阈值 pursue≥75 / 通知灵昭≥85")
    from lib.jobs import _append_inbox_task

    _append_inbox_task(data_dir, agent, "\n".join(lines), priority="normal")
    stats["notified"] = {"agent": agent, "new_total": new_total}


def main() -> int:
    ap = argparse.ArgumentParser(description="platform-scout 线索抓取")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--platform", help="仅跑指定 platform id（v2ex / github_issues）")
    ap.add_argument("--dry-run", action="store_true", help="只抓取统计，不写盘")
    args = ap.parse_args()

    try:
        stats = run_scout(args.data_dir, platform_id=args.platform, dry_run=args.dry_run)
    except Exception as exc:
        print(f"[platform-scout] error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
