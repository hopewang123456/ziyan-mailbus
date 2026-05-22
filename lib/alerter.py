"""ziyan-mailbus 告警系统

健康异常时推送告警消息给管理员或指定 Agent。"""
import os
from typing import Optional
from datetime import datetime

from .utils import json_read, json_write, _now_iso
from .models import Message, MsgType, MsgStatus, Priority


ALERT_FILE = "alerts.json"  # 告警记录文件（store 目录下）


def get_alerts_path(data_dir: str) -> str:
    return os.path.join(data_dir, ALERT_FILE)


def load_alerts(data_dir: str) -> dict:
    return json_read(get_alerts_path(data_dir), {"alerts": [], "last_alert_at": ""})


def save_alerts(data_dir: str, alerts_data: dict):
    json_write(get_alerts_path(data_dir), alerts_data)


def push_alert(data_dir: str, alert_type: str, severity: str,
               agent: str, message: str):
    """
    记录一条告警 + 推送到管理员 inbox。

    alert_type: agent_offline / agentmemory_down / disk_full / inbox_overflow / key_missing
    severity: info / warn / critical
    """
    alerts = load_alerts(data_dir)
    now = _now_iso()

    alert = {
        "id": f"alert-{int(datetime.now().timestamp())}",
        "type": alert_type,
        "severity": severity,
        "agent": agent,
        "message": message,
        "created_at": now,
    }
    alerts["alerts"].append(alert)
    alerts["last_alert_at"] = now

    # 只保留最近 100 条
    if len(alerts["alerts"]) > 100:
        alerts["alerts"] = alerts["alerts"][-100:]

    save_alerts(data_dir, alerts)

    # 推送到第一个有 type=hermes 的 agent 的 inbox（管理员）
    # 如果找不到，不推送
    _notify_admin(data_dir, alert)


def _notify_admin(data_dir: str, alert: dict):
    """推送给管理员（第一个 hermes 类型的 agent）"""
    config_path = os.path.join(data_dir, "config.json")
    config = json_read(config_path, {})
    if not config:
        return

    agents = config.get("agents", {})
    # 找管理员: 优先找 子言，没有则找第一个 hermes 类型
    admin_name = None
    for name, cfg in agents.items():
        if name == "ziyan" or name == "子言":
            admin_name = name
            break
    if not admin_name:
        for name, cfg in agents.items():
            if cfg.get("type") in ("hermes", "hermes_profile"):
                admin_name = name
                break
    if not admin_name:
        return

    from .utils import build_message
    severity_icon = {"critical": "🔴", "warn": "⚠️", "info": "ℹ️"}
    icon = severity_icon.get(alert["severity"], "ℹ️")

    msg = build_message(
        from_="mailbus",
        to=admin_name,
        content=f"{icon} 【{alert['severity'].upper()}】{alert['message']}\n类型: {alert['type']}\nAgent: {alert['agent']}",
        msg_type=MsgType.NOTICE,
        priority=Priority.URGENT if alert["severity"] in ("critical", "warn") else Priority.NORMAL,
    )

    from .utils import resolve_paths
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{admin_name}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": admin_name, "has_unread": False, "messages": [], "since": _now_iso()})
    from .models import Inbox
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg.to_dict())
    json_write(inbox_file, inbox.to_dict())


def get_recent_alerts(data_dir: str, limit: int = 10) -> list:
    """获取最近告警"""
    alerts = load_alerts(data_dir)
    return alerts["alerts"][-limit:]
