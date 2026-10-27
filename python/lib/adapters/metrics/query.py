"""metrics query — 统一查询协议（B2：metric + granularity + hours，前端大盘与 AI 助手共同消费）。"""
from __future__ import annotations

from typing import Any, Dict, List

from lib.adapters.metrics.collector import collect_all_points, collect_point
from lib.adapters.metrics.manifest import load_manifest
from lib.adapters.metrics.store import append_samples, read_series


def query(
    data_dir: str,
    metric_id: str = "",
    *,
    granularity: str = "point",
    hours: int = 24,
) -> Dict[str, Any]:
    """granularity=point：现算单值（或多指标全量）；=1h 等窗口：读时序序列。"""
    manifest = load_manifest(data_dir)
    known = {str(m.get("id")): m for m in manifest.get("metrics") or []}

    if granularity == "point":
        if metric_id:
            return {"status": "ok", "points": [collect_point(metric_id, data_dir)]}
        return {"status": "ok", "points": collect_all_points(data_dir)}

    # 窗口查询：读时序（无历史时回退现算单点，保持大盘可用）
    if metric_id and metric_id not in known:
        return {"status": "error", "error": "unknown_metric", "metric": metric_id}
    ids = [metric_id] if metric_id else list(known)
    series: List[Dict[str, Any]] = []
    for mid in ids:
        rows = read_series(data_dir, mid, hours=hours)
        if not rows:
            p = collect_point(mid, data_dir)
            rows = [{"ts": "", "value": p.get("value")}] if p.get("value") is not None else []
        series.append({"metric": mid, "points": rows})
    return {"status": "ok", "series": series}


def snapshot(data_dir: str) -> Dict[str, Any]:
    """采集当前全部 point 指标并落时序（scheduler 周期调用 / 手动触发）。"""
    points = collect_all_points(data_dir)
    written = append_samples(
        data_dir,
        [{"metric": p.get("metric"), "value": p.get("value")} for p in points],
    )
    # B5：采集后评估告警规则（触发→写告警+给子言发消息；30 分钟去抖）
    from lib.adapters.metrics.rules import evaluate_rules

    values = {p["metric"]: p["value"] for p in points if p.get("value") is not None}
    alert_out = evaluate_rules(data_dir, values)
    return {
        "status": "ok",
        "collected": len(points),
        "written": written,
        "alerts_fired": [r.get("id") for r in alert_out.get("fired") or []],
    }
