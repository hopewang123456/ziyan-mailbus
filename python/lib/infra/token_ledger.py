"""E3 token 台账 — 每次 push（含 internal LLM）记账，今日视图可归因到工单。

记录语义（D5）：
- kind=push          agent CLI 被拉起（dispatch 路径 / scan 推送路径），按 prompt
                     字符估算 token（source=estimated，agent 侧真实消耗以回执为准）
- kind=internal_llm  路由/规划等内部 LLM 调用（次数 + 可选估算）
- kind=result_usage  agent 回执携带的 usage（source=reported，最高置信）

存储：store/ledger/tokens-YYYY-MM-DD.jsonl 日分片——今日视图 O(1 天文件)，
天然可按日归档/清理。预算：mailbus_automation.token_budget.daily_est_tokens
（估算口径日上限，0=不设限；超限只告警不硬停——§5-4 拍板）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional

from lib.infra.utils import json_read, _now_iso


def _ledger_dir(data_dir: str) -> str:
    return os.path.join(data_dir, "ledger")


def _day_path(data_dir: str, day: str = "") -> str:
    d = day or datetime.now().strftime("%Y-%m-%d")
    return os.path.join(_ledger_dir(data_dir), f"tokens-{d}.jsonl")


def _est_tokens_from_chars(chars: int) -> int:
    """CLI 层估算：~4 字符/token（中文场景偏保守，仅标注 estimated）。"""
    return max(0, int(chars)) // 4


def _append(data_dir: str, entry: dict[str, Any]) -> None:
    if not data_dir:
        return
    os.makedirs(_ledger_dir(data_dir), exist_ok=True)
    entry["ts"] = _now_iso()
    with open(_day_path(data_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record_push(
    data_dir: str,
    *,
    agent: str,
    task_id: str = "",
    step_id: str = "",
    framework: str = "",
    trigger: str = "dispatch",
    attempt: int = 1,
    ok: bool = True,
    prompt_chars: int = 0,
) -> None:
    _append(data_dir, {
        "kind": "push",
        "agent": agent,
        "task_id": task_id,
        "step_id": step_id,
        "framework": framework,
        "trigger": trigger,
        "attempt": int(attempt),
        "ok": bool(ok),
        "est_tokens": _est_tokens_from_chars(prompt_chars),
        "source": "estimated" if prompt_chars else "counted",
    })


def record_internal_llm(
    data_dir: str,
    *,
    task_id: str = "",
    purpose: str = "",
    provider: str = "",
    ok: bool = True,
    prompt_chars: int = 0,
) -> None:
    _append(data_dir, {
        "kind": "internal_llm",
        "agent": "internal-llm",
        "task_id": task_id,
        "purpose": purpose,
        "provider": provider,
        "ok": bool(ok),
        "est_tokens": _est_tokens_from_chars(prompt_chars),
        "source": "estimated" if prompt_chars else "counted",
    })


def record_result_usage(
    data_dir: str,
    *,
    task_id: str,
    step_id: str = "",
    agent: str = "",
    usage: dict[str, Any],
) -> None:
    """回执携带 usage（agent 上报，最高置信）。usage 形如 {input,output,total,by}。"""
    if not isinstance(usage, dict):
        return
    total = usage.get("total") or usage.get("total_tokens")
    try:
        total = int(total or 0)
    except (TypeError, ValueError):
        total = 0
    _append(data_dir, {
        "kind": "result_usage",
        "agent": agent,
        "task_id": task_id,
        "step_id": step_id,
        "usage": {k: usage.get(k) for k in ("input", "output", "total", "total_tokens", "model", "by") if usage.get(k) is not None},
        "est_tokens": total,
        "source": "reported",
    })


def extract_usage_from_result(result: dict[str, Any]) -> Optional[dict[str, Any]]:
    """从 step-result 提取 usage（容错多形态：usage / token_usage / usage_reported）。"""
    if not isinstance(result, dict):
        return None
    for key in ("usage", "token_usage", "usage_reported"):
        u = result.get(key)
        if isinstance(u, dict):
            return u
    return None


def _read_day(data_dir: str, day: str = "") -> list[dict[str, Any]]:
    path = _day_path(data_dir, day)
    if not os.path.isfile(path):
        return []
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def daily_budget(data_dir: str) -> int:
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    try:
        return int(((cfg.get("mailbus_automation") or {}).get("token_budget") or {}).get("daily_est_tokens") or 0)
    except (TypeError, ValueError):
        return 0


def today_summary(data_dir: str) -> dict[str, Any]:
    """驾驶舱今日视图：总估算、按 agent/工单/类型聚合、预算状态、尖峰分钟。"""
    entries = _read_day(data_dir)
    total = 0
    by_agent: dict[str, int] = {}
    by_task: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    by_minute: dict[str, int] = {}
    calls = 0
    for e in entries:
        est = int(e.get("est_tokens") or 0)
        total += est
        calls += 1
        a = str(e.get("agent") or "?")
        t = str(e.get("task_id") or "")
        k = str(e.get("kind") or "?")
        by_agent[a] = by_agent.get(a, 0) + est
        by_kind[k] = by_kind.get(k, 0) + est
        if t:
            by_task[t] = by_task.get(t, 0) + est
        minute = str(e.get("ts") or "")[:16]
        if minute:
            by_minute[minute] = by_minute.get(minute, 0) + est
    peak_minute, peak_tokens = ("", 0)
    if by_minute:
        peak_minute, peak_tokens = max(by_minute.items(), key=lambda kv: kv[1])

    limit = daily_budget(data_dir)
    top_tasks = sorted(by_task.items(), key=lambda kv: -kv[1])[:5]
    return {
        "day": datetime.now().strftime("%Y-%m-%d"),
        "calls": calls,
        "est_tokens_total": total,
        "by_kind": by_kind,
        "by_agent": dict(sorted(by_agent.items(), key=lambda kv: -kv[1])),
        "top_tasks": [{"task_id": t, "est_tokens": v} for t, v in top_tasks],
        "peak": {"minute": peak_minute, "est_tokens": peak_tokens},
        "budget": {
            "daily_est_tokens": limit,
            "exceeded": bool(limit) and total > limit,
            "used_pct": round(total * 100 / limit, 1) if limit else None,
        },
    }


def by_task(data_dir: str, task_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """单工单下钻（尖峰 30 秒归因的数据面）。"""
    hits: list[dict[str, Any]] = []
    if not task_id or not data_dir or not os.path.isdir(_ledger_dir(data_dir)):
        return hits
    for fname in sorted(os.listdir(_ledger_dir(data_dir)), reverse=True):
        if not (fname.startswith("tokens-") and fname.endswith(".jsonl")):
            continue
        for e in _read_day(data_dir, fname[len("tokens-"):-len(".jsonl")]):
            if str(e.get("task_id") or "") == task_id:
                hits.append(e)
        if len(hits) >= limit:
            break
    return hits[:limit]
