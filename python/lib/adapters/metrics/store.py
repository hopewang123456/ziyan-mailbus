"""metrics store — 时序追加存储（B3：独立于业务 store，环形保留窗口）。

文件：``{data_dir}/metrics/timeseries.jsonl``（每行 {ts, metric, value}）。
保留窗口默认 7 天（manifest 顶层 retention_days 可调）；超窗行在追加时惰性清理。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from lib.infra.clock import now_utc_dt
from lib.infra.utils import parse_iso_dt


def _ts_path(data_dir: str) -> str:
    return os.path.join(data_dir, "metrics", "timeseries.jsonl")


def retention_days(data_dir: str = "") -> int:
    from lib.adapters.metrics.manifest import load_manifest

    try:
        return int(load_manifest(data_dir).get("retention_days") or 7)
    except Exception:
        return 7


def append_samples(data_dir: str, samples: List[Dict[str, Any]]) -> int:
    """追加一批 {metric, value} 采样（时间戳由本函数打）；惰性清理超窗。"""
    if not samples:
        return 0
    path = _ts_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    now = now_utc_dt().isoformat()
    lines = [
        json.dumps({"ts": now, "metric": s.get("metric"), "value": s.get("value")},
                   ensure_ascii=False)
        for s in samples
        if s.get("value") is not None and not s.get("error")
    ]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    _maybe_compact(data_dir)
    return len(lines)


def read_series(data_dir: str, metric_id: str, *, hours: int = 24) -> List[Dict[str, Any]]:
    """读取某指标近 N 小时序列（升序）。"""
    path = _ts_path(data_dir)
    if not os.path.isfile(path):
        return []
    import datetime as _dt

    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
    out: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("metric") != metric_id:
                continue
            ts = parse_iso_dt(str(row.get("ts") or ""))
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_dt.timezone.utc)
            if ts >= cutoff:
                out.append({"ts": row.get("ts"), "value": row.get("value")})
    return out


def _maybe_compact(data_dir: str) -> None:
    """追加时低概率（约 1/64）做一次超窗压缩。"""
    import datetime as _dt
    import random

    if random.random() > 1 / 64:
        return
    path = _ts_path(data_dir)
    if not os.path.isfile(path):
        return
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=retention_days(data_dir))
    kept: List[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                row = json.loads(s)
                ts = parse_iso_dt(str(row.get("ts") or ""))
                if ts is None:
                    kept.append(s)
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=_dt.timezone.utc)
                if ts >= cutoff:
                    kept.append(s)
            except Exception:
                continue
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))
    os.replace(tmp, path)
