"""E2 死信队列（DLQ）— push 终局失败与环路拦截的落点。

最小语义：
- append-only JSONL（store/dlq/dlq-<YYYY-Www>.jsonl），带消息快照可人工重放；
- 写入方：pusher 终局失败（CLI 全模型不可用）、forward 环路拦截；
- 读取方：`mailbus dlq` CLI / 驾驶舱（D6 统一待裁决收件箱的数据面）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from lib.infra.utils import json_read, json_write, _now_iso


def _dlq_dir(data_dir: str) -> str:
    return os.path.join(data_dir, "dlq")


def _week_path(data_dir: str) -> str:
    dt = datetime.now(timezone.utc)
    week = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
    return os.path.join(_dlq_dir(data_dir), f"dlq-{week}.jsonl")


def dlq_append(data_dir: str, entry: dict[str, Any]) -> str:
    """追加一条死信记录；entry 需含 reason，其余字段（msg_id/task_id/agent/snapshot）尽量全。"""
    if not data_dir or not isinstance(entry, dict):
        return ""
    os.makedirs(_dlq_dir(data_dir), exist_ok=True)
    record = {
        "ts": _now_iso(),
        "reason": entry.get("reason") or "unknown",
        "msg_id": entry.get("msg_id") or "",
        "task_id": entry.get("task_id") or "",
        "agent": entry.get("agent") or "",
        "error": entry.get("error") or "",
        "snapshot": entry.get("snapshot") or {},
    }
    path = _week_path(data_dir)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def dlq_recent(data_dir: str, limit: int = 20) -> list[dict[str, Any]]:
    """最近 N 条死信（跨周文件，按 ts 倒序）。"""
    if not data_dir or not os.path.isdir(_dlq_dir(data_dir)):
        return []
    records: list[dict[str, Any]] = []
    for fname in sorted(os.listdir(_dlq_dir(data_dir)), reverse=True):
        if not fname.startswith("dlq-") or not fname.endswith(".jsonl"):
            continue
        with open(os.path.join(_dlq_dir(data_dir), fname), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    records.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
    return records[: max(0, int(limit))]


# ── forward 环路防护（A↔B 互转 hop 上限）──

_FWD_LEDGER = "fwd-hops.json"


def _fwd_ledger_path(data_dir: str) -> str:
    return os.path.join(_dlq_dir(data_dir), _FWD_LEDGER)


def forward_hop_check(data_dir: str, root_id: str, *, max_hops: int = 8) -> tuple[bool, int]:
    """环路防护：同一 root（original_msg_id）的转发跳数 +1 并检查上限。

    返回 (allowed, hops_after_increment)。超限时调用方应拒转并写 DLQ。
    ledger 为内存态持久化（store/dlq/fwd-hops.json），root 粒度计数。
    """
    os.makedirs(_dlq_dir(data_dir), exist_ok=True)
    ledger_path = _fwd_ledger_path(data_dir)
    ledger = json_read(ledger_path, {})
    key = root_id or ""
    if not key:
        # 无 root 的转发无法稳定计数：放行但标注 hops=1（不阻断普通一次性转发）
        return True, 1
    hops = int(ledger.get(key, {}).get("count") or 0) + 1
    ledger[key] = {"count": hops, "last_at": _now_iso()}
    json_write(ledger_path, ledger)
    return hops <= max_hops, hops
