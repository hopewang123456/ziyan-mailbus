"""告警自动解除模块

在 run_housekeeping 中被调用。扫描所有活跃告警并检测解除条件。
"""
import os
from lib.infra.clock import now_ts as clock_now_ts
from lib.infra import mbus_log
from lib.composition import get_ops
from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import json_read


def resolve(data_dir: str, paths: dict):
    """主入口：扫描活跃告警，检测解除条件"""
    ops = get_ops()
    alerts = ops.load_alerts(data_dir)
    now_ts = int(clock_now_ts())

    for alert in alerts.get("alerts", []):
        if alert.get("status") != "active":
            continue
        atype = alert.get("type", "")
        agent_name = alert.get("agent", "")
        resolved = _check_condition(atype, agent_name, alert, data_dir, paths, now_ts)
        if resolved:
            ops.resolve_alert(data_dir, alert["id"], "auto")
            mbus_log.info("[resolve] alert %s auto-resolved", alert["id"])

    # 清理 7 天前的已解除/过期告警
    cutoff = now_ts - 7 * 86400
    alerts = ops.load_alerts(data_dir)
    before = len(alerts["alerts"])
    alerts["alerts"] = [a for a in alerts["alerts"]
                        if a.get("status") == "active"
                        or int(a.get("id", "0").replace("alert-", "0")) > cutoff]
    if len(alerts["alerts"]) < before:
        ops.save_alerts(data_dir, alerts)
        mbus_log.info("[resolve] purged %d expired alerts", before - len(alerts["alerts"]))


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

    elif atype == "key_missing":
        config = json_read(os.path.join(data_dir, "config.json"), {})
        if config:
            for k in get_ops().check_api_keys(config):
                if k.get("agent") == agent_name and k.get("key_status") == "valid":
                    return True

    return False
