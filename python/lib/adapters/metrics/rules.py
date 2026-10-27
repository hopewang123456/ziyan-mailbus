"""指标告警规则引擎（P2 B5）— 阈值规则配置化 + 触发动作走总线。

SoT：`shared/config/mailbus/alert-rules.json`（seed）+ `{data_dir}/config/alert-rules.json`（覆盖）。
动作：write_alert（写告警日志）+ notify_ziyan（给子言 inbox 发消息——D1 被唤起通道）。
去抖：同一规则在 cooldown_seconds（默认 1800s）内不重复触发（store 侧状态文件记 last_fired）。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from lib.infra.constants import MAILBUS_ROOT
from lib.infra.utils import json_read, json_write

_SEED = os.path.join(str(MAILBUS_ROOT), "config", "mailbus", "alert-rules.json")
_OPS = {
    "gt": lambda v, t: v > t,
    "ge": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "le": lambda v, t: v <= t,
    "eq": lambda v, t: v == t,
}
_COOLDOWN_SECONDS = 1800


def load_rules(data_dir: str = "") -> List[Dict[str, Any]]:
    doc = json_read(_SEED, {"rules": []})
    by_id = {str(r.get("id")): dict(r) for r in doc.get("rules") or [] if r.get("id")}
    if data_dir:
        for r in json_read(os.path.join(data_dir, "config", "alert-rules.json"), {}).get("rules") or []:
            rid = str(r.get("id") or "")
            if rid in by_id:
                by_id[rid].update(r)
    return list(by_id.values())


def _state_path(data_dir: str) -> str:
    return os.path.join(data_dir, "metrics", "alert-rules-state.json")


def _now_ts() -> float:
    import time

    return time.time()


def evaluate_rules(data_dir: str, metric_values: Dict[str, float]) -> Dict[str, Any]:
    """对当前指标值评估全部规则；返回 {fired: [rule...], skipped_cooldown: [id...]}。

    动作在评估内执行（write_alert / notify_ziyan），失败不阻断其它规则。
    """
    state = json_read(_state_path(data_dir), {"fired": {}})
    fired_now: List[Dict[str, Any]] = []
    skipped: List[str] = []

    for rule in load_rules(data_dir):
        if not rule.get("enabled", True):
            continue
        rid = str(rule.get("id"))
        metric = str(rule.get("metric") or "")
        op = _OPS.get(str(rule.get("op") or "gt"))
        value = metric_values.get(metric)
        if op is None or value is None:
            continue
        try:
            threshold = float(rule.get("threshold"))
        except (TypeError, ValueError):
            continue
        if not op(float(value), threshold):
            continue
        last = float((state.get("fired") or {}).get(rid) or 0)
        if _now_ts() - last < _COOLDOWN_SECONDS:
            skipped.append(rid)
            continue

        fired_now.append(rule)
        state.setdefault("fired", {})[rid] = _now_ts()
        actions = rule.get("actions") or ["write_alert"]
        sev = str(rule.get("severity") or "warn")
        msg = f"[{sev}] 指标告警：{metric} = {value}（规则 {rid}，阈值 {'>' if rule.get('op')=='gt' else rule.get('op')} {threshold:g}）"
        if "write_alert" in actions:
            try:
                from lib.composition import push_alert

                push_alert(data_dir, sev, "metrics-rule", msg)
            except Exception:
                pass
        if "notify_ziyan" in actions:
            try:
                _send_msg_to_ziyan(data_dir, msg)
            except Exception:
                pass

    if fired_now:
        os.makedirs(os.path.dirname(_state_path(data_dir)), exist_ok=True)
        json_write(_state_path(data_dir), state)
    return {"fired": fired_now, "skipped_cooldown": skipped}


def _send_msg_to_ziyan(data_dir: str, content: str) -> None:
    """复用 inbox 总线（send-msg 同构逻辑，直写避免 HTTP 自调用）。"""
    from lib.infra.utils import build_message, json_write, resolve_paths

    msg = build_message("metrics-alerts", "ziyan", content, "notice", "normal").to_dict()
    paths = resolve_paths(data_dir)
    inbox_file = os.path.join(paths["inbox"], "ziyan", "inbox.json")
    doc = json_read(inbox_file, {"agent": "ziyan", "messages": []})
    doc.setdefault("messages", []).append(msg if isinstance(msg, dict) else json.loads(json.dumps(msg, default=str)))
    doc["has_unread"] = True
    json_write(inbox_file, doc)


def patch_rule(data_dir: str, rule_id: str, fields: Dict[str, Any]) -> Dict[str, Any] | None:
    """管理中心编辑规则（enabled/threshold/severity/note/actions 白名单）。"""
    allowed = {"enabled", "threshold", "severity", "note", "actions"}
    unknown = [k for k in fields if k not in allowed]
    if unknown:
        raise ValueError(f"不可编辑字段: {', '.join(unknown)}")
    if not any(r.get("id") == rule_id for r in load_rules(data_dir)):
        return None
    path = os.path.join(data_dir, "config", "alert-rules.json")
    doc = json_read(path, {"rules": []})
    rules = doc.get("rules") or []
    hit = next((r for r in rules if r.get("id") == rule_id), None)
    if hit is None:
        hit = {"id": rule_id}
        rules.append(hit)
    hit.update(fields)
    doc["rules"] = rules
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_write(path, doc)
    # 合成视图返回
    base = next(r for r in json_read(_SEED, {"rules": []})["rules"] if r.get("id") == rule_id)
    base.update(hit)
    return base
