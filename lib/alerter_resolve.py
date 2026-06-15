"""告警自动解除模块

在 run_housekeeping 中被调用。扫描所有活跃告警并检测解除条件。
"""
import time as _time
from .alerter import load_alerts, save_alerts, resolve_alert
from .tracker import TaskTracker
from .utils import json_read


def resolve(data_dir: str, paths: dict):
    """主入口：扫描活跃告警，检测解除条件"""
    alerts = load_alerts(data_dir)
    now_ts = int(_time.time())

    for alert in alerts.get("alerts", []):
        if alert.get("status") != "active":
            continue
        atype = alert.get("type", "")
        agent_name = alert.get("agent", "")
        resolved = _check_condition(atype, agent_name, alert, data_dir, paths, now_ts)
        if resolved:
            resolve_alert(data_dir, alert["id"], "auto")
            print("  [resolve] 告警%s已自动解除" % alert["id"])

    # 清理 7 天前的已解除/过期告警
    cutoff = now_ts - 7 * 86400
    alerts = load_alerts(data_dir)
    before = len(alerts["alerts"])
    alerts["alerts"] = [a for a in alerts["alerts"]
                        if a.get("status") == "active"
                        or int(a.get("id", "0").replace("alert-", "0")) > cutoff]
    if len(alerts["alerts"]) < before:
        save_alerts(data_dir, alerts)
        print("  [resolve] 清理了 %d 条过期告警" % (before - len(alerts["alerts"])))


def _check_condition(atype, agent_name, alert, data_dir, paths, now_ts):
    if atype == "inbox_overflow":
        inbox_file = "%s/inbox/%s/inbox.json" % (data_dir, agent_name)
        try:
            inbox_data = json_read(inbox_file, {})
            if inbox_data:
                msgs = inbox_data.get("messages", [])
                if len(msgs) < 30:
                    return True
        except Exception:
            pass

    elif atype == "agent_offline":
        hb_file = "%s/heartbeat.json" % data_dir
        try:
            hb_data = json_read(hb_file, {})
            agent_status = hb_data.get("agents", {}).get(agent_name, {})
            if agent_status.get("status") == "online":
                return True
        except Exception:
            pass

    elif atype == "task_timeout":
        TRA = TaskTracker(data_dir)
        for t in TRA.list_all():
            chain = t.get("chain", [])
            if chain and chain[-1].get("status") in ("completed", "done"):
                return True

    elif atype == "pipeline_loop":
        aid = alert.get("id", "0").replace("alert-", "") or "0"
        if now_ts - int(aid) > 600:
            return True

    elif atype == "push_failed":
        aid = alert.get("id", "0").replace("alert-", "") or "0"
        if now_ts - int(aid) > 300:
            return True

    return False
