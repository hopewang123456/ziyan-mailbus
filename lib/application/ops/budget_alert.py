"""Wave 5 E10 — token 预算告警动作（§5-4 拍板：默认告警，不硬停）。

日预算（mailbus_automation.token_budget.daily_est_tokens，估算口径）首次超限：
- push_alert（alerts.json + 管理员 inbox，alerter 自带 active 去重）；
- 每日只动作一次（ledger/budget-alert-<day>.flag 标记）；
- 由 scheduler 周期任务 / scan housekeeping 调用。
"""
from __future__ import annotations

import os
from typing import Any

from lib.infra.utils import _now_iso, json_write


def _flag_path(data_dir: str) -> str:
    from lib.infra.token_ledger import _day_path  # 同目录共处

    return os.path.join(os.path.dirname(_day_path(data_dir)), "budget-alerted.flag")


def check_token_budget(data_dir: str) -> dict[str, Any]:
    """检查并（首次）触发告警。幂等：当日已告警则跳过。"""
    from lib.infra.token_ledger import today_summary

    summary = today_summary(data_dir)
    budget = summary.get("budget") or {}
    limit = int(budget.get("daily_est_tokens") or 0)
    exceeded = bool(budget.get("exceeded"))
    out: dict[str, Any] = {
        "day": summary.get("day"),
        "limit": limit,
        "est_tokens_total": summary.get("est_tokens_total"),
        "exceeded": exceeded,
        "action": "none",
    }
    if not limit or not exceeded:
        return out

    flag = _flag_path(data_dir)
    if os.path.isfile(flag):
        out["action"] = "already_alerted_today"
        return out

    from lib.composition import push_alert

    push_alert(
        data_dir,
        "token_budget_exceeded",
        "warn",
        agent="internal-llm",
        message=(
            f"今日 token 估算消耗 {summary.get('est_tokens_total')} 已超日预算 {limit}"
            f"（{budget.get('used_pct')}%）。Top 工单: "
            + "; ".join(f"{t.get('task_id')}={t.get('est_tokens')}" for t in (summary.get("top_tasks") or [])[:3])
            + "。下钻: mailbus tokens --task <id>"
        ),
        dedupe_key=f"token-budget-{summary.get('day')}",
    )
    os.makedirs(os.path.dirname(flag), exist_ok=True)
    json_write(flag, {"day": summary.get("day"), "alerted_at": _now_iso(),
                      "total": summary.get("est_tokens_total"), "limit": limit})
    out["action"] = "alerted"
    return out
