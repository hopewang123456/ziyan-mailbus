"""M1 W4 验收观察项对账：六项健康检查一条命令（人读表 + --json 供宿主哨兵消费）。

观察项来自验收周（2026-09-20）的六条盯项，2026-09 停摆事故后固化为代码：
patrol/daily 产出连续性、token 台账、待裁决队列压积、serve API 探活、
scheduler 心跳（cron.log 最新 job 完成时间）。

只读 store 文件系统 + 一个可选的 health ping——mailbus 全死时前五项仍可出数
（serve 探活会红），这正是宿主哨兵（W3）需要的形态。
"""
import glob
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta

from lib.infra.clock import now_dt
from lib.infra.utils import json_read
from lib.interfaces.clock import TZ_CST

_OK, _INFO, _WARN = "ok", "info", "warn"

_CRON_DONE_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})[+-]\d{4}\] scheduler job=\S+ done")

# store 文件名/日志时间戳均为 +0800 口径（与 clock 一致）。
# 不可用 datetime.now().astimezone().tzinfo：load_mailbus_env 设置 TZ 后，
# Windows Python 会把本地时区判成 UTC，年龄会整体偏 8 小时。
_LOCAL_TZ = TZ_CST


def _parse_ts(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_LOCAL_TZ)
    except ValueError:
        return None


def _parse_local(s: str, fmt: str):
    try:
        return datetime.strptime(s, fmt).replace(tzinfo=_LOCAL_TZ)
    except ValueError:
        return None


def _patrol_status(data_dir: str, now) -> dict:
    files = sorted(glob.glob(os.path.join(data_dir, "reports", "patrol", "*.md")))
    if not files:
        return {"status": _WARN, "detail": "no patrol reports ever"}
    m = re.search(r"(\d{8})-(\d{6})", os.path.basename(files[-1]))
    if not m:
        return {"status": _WARN, "detail": f"unparsable name: {os.path.basename(files[-1])}"}
    last = _parse_local(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    if last is None:
        return {"status": _WARN, "detail": f"unparsable name: {os.path.basename(files[-1])}"}
    age_h = (now - last).total_seconds() / 3600
    day_ago = now - timedelta(hours=24)
    count_24h = sum(
        1 for f in files
        if (mm := re.search(r"(\d{8})-(\d{6})", os.path.basename(f)))
        and (_parse_local(mm.group(1) + mm.group(2), "%Y%m%d%H%M%S") or now) >= day_ago
    )
    status = _OK if age_h <= 2.5 else (_INFO if age_h <= 14 else _WARN)
    if count_24h == 0:
        status = _WARN
    return {
        "status": status,
        "detail": f"latest {age_h:.1f}h ago, {count_24h} in 24h (hourly expected)",
        "latest": last.strftime("%Y-%m-%d %H:%M"),
        "age_hours": round(age_h, 1),
        "count_24h": count_24h,
    }


def _daily_status(data_dir: str, now) -> dict:
    days = {
        os.path.basename(p)[: -len(".md")]
        for p in glob.glob(os.path.join(data_dir, "reports", "daily", "*.md"))
    }
    missing = []
    for i in range(7):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in days:
            continue
        # 当天 11:35（daily_report cron）之前不算缺
        if i == 0 and (now.hour, now.minute) < (11, 35):
            continue
        missing.append(d)
    status = _OK if not missing else (_INFO if len(missing) <= 2 else _WARN)
    return {"status": status, "detail": f"missing {missing or 'none'} in last 7d", "missing": missing}


def _ledger_status(data_dir: str, now) -> dict:
    files = sorted(glob.glob(os.path.join(data_dir, "ledger", "tokens-*.jsonl")))
    today = now.strftime("%Y-%m-%d")
    today_tokens = 0
    today_path = os.path.join(data_dir, "ledger", f"tokens-{today}.jsonl")
    if os.path.isfile(today_path):
        with open(today_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    today_tokens += int(json.loads(line).get("est_tokens") or 0)
                except (ValueError, AttributeError):
                    pass
    last = os.path.basename(files[-1])[7:-6] if files else ""
    # 无今日台账 = 今天无 token 活动，正常（info）；连续多日全无才可疑
    return {
        "status": _OK,
        "detail": f"today {today_tokens} tok; last ledger {last or 'none'}",
        "today_tokens": today_tokens,
        "last_file": last,
    }


def _queue_status(data_dir: str, now) -> dict:
    doc = json_read(os.path.join(data_dir, "human-queue.json"), {})
    items = doc.get("items") if isinstance(doc, dict) else doc
    items = items or []
    # 教训（09-28）：open 判定必须排除 approved/denied，否则误报压队列
    open_items = [
        i for i in items
        if isinstance(i, dict)
        and str(i.get("status") or "pending") not in ("approved", "denied", "resolved", "closed", "done")
    ]
    oldest_h = 0.0
    if open_items:
        created = _parse_ts(str(open_items[0].get("created_at") or "")[:19])
        if created:
            oldest_h = (now - created).total_seconds() / 3600
    status = _OK
    if open_items and oldest_h > 48:
        status = _WARN
    elif open_items and oldest_h > 24:
        status = _INFO
    return {
        "status": status,
        "detail": f"{len(open_items)} open, oldest {oldest_h:.0f}h",
        "open": len(open_items),
        "oldest_hours": round(oldest_h, 1),
    }


def _api_status(api_base: str) -> dict:
    try:
        with urllib.request.urlopen(f"{api_base.rstrip('/')}/api/health", timeout=3) as resp:
            ok = 200 <= resp.status < 300
        return {"status": _OK if ok else _WARN, "detail": f"health {resp.status}"}
    except Exception as exc:
        return {"status": _WARN, "detail": f"unreachable: {exc}"}


def _scheduler_status(data_dir: str, now) -> dict:
    path = os.path.join(data_dir, "cron.log")
    if not os.path.isfile(path):
        return {"status": _WARN, "detail": "no cron.log"}
    last_ts = None
    # 只扫尾部（文件可达数十万行）
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - 200_000))
        tail = fh.read().decode("utf-8", "replace")
    for m in _CRON_DONE_RE.finditer(tail):
        last_ts = m.group(1)
    if not last_ts:
        return {"status": _WARN, "detail": "no scheduler job records"}
    t = _parse_ts(last_ts)
    if not t:
        return {"status": _WARN, "detail": f"unparsable ts {last_ts}"}
    age_min = (now - t).total_seconds() / 60
    status = _OK if age_min <= 10 else (_INFO if age_min <= 120 else _WARN)
    return {"status": status, "detail": f"last job done {age_min:.0f}min ago", "age_minutes": round(age_min)}


def acceptance_status(data_dir: str, *, api_base: str = "http://127.0.0.1:9814") -> dict:
    now = now_dt()
    items = {
        "serve_api": _api_status(api_base),
        "scheduler": _scheduler_status(data_dir, now),
        "patrol": _patrol_status(data_dir, now),
        "daily": _daily_status(data_dir, now),
        "ledger": _ledger_status(data_dir, now),
        "human_queue": _queue_status(data_dir, now),
    }
    ok = all(v["status"] != _WARN for v in items.values())
    return {"ok": ok, "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"), "items": items}


def format_acceptance_text(report: dict) -> str:
    icon = {"ok": "✓", "info": "·", "warn": "✗"}
    lines = [f"\n🩺 mailbus acceptance status — {report['checked_at']}  ({'OK' if report['ok'] else 'HAS WARNINGS'})"]
    for key, item in report["items"].items():
        lines.append(f"  {icon.get(item['status'], '?')} {key:<12} {item['detail']}")
    lines.append("")
    return "\n".join(lines)
