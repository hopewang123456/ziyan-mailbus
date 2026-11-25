"""B7：告警规则、告警生命周期、通知冷却与审计查询/CSV。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as test_client:
        yield test_client


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return _headers(response.json()["token"])


def _rule(client: TestClient, headers, **overrides) -> dict:
    payload = {
        "name": "Agent 离线",
        "alert_type": "agent_offline",
        "threshold": 60,
        "channel": "inapp",
        "silence_seconds": 600,
    }
    payload.update(overrides)
    response = client.post("/api/alert-rules", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _set_agent_seen(client: TestClient, seconds_ago: float) -> None:
    """直接写入 Agent 心跳时间，构造确定性的离线/恢复场景。"""
    from dataclasses import replace

    from mailbus.core.agents.models import Agent

    container = client.app.state.container
    now = container.clock.now()
    with container.uow() as uow:
        agent = uow.agents.get("agent_test")
        if agent is None:
            agent = Agent(
                agent_id="agent_test", name="测试 Agent", framework="test",
                enabled=True, created_at=now, updated_at=now,
            )
        uow.agents.save(replace(
            agent, last_seen_at=now - timedelta(seconds=seconds_ago)
        ))
        uow.commit()


def _evaluate(client: TestClient) -> int:
    return client.app.state.container.ops.evaluate()


def _notifications(client: TestClient, headers) -> list[dict]:
    response = client.get(
        "/api/audit", params={"action": "alert.notified"}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_alert_lifecycle_and_notification_cooldown(client):
    headers = _bootstrap(client)
    rule = _rule(client, headers)
    assert rule["enabled"] is True
    assert rule["threshold"] == 60

    listed = client.get("/api/alert-rules", headers=headers).json()
    assert listed["total"] == 1 and listed["items"][0]["rule_id"] == rule["rule_id"]
    assert client.get("/api/alerts", headers=headers).json()["items"] == []

    _set_agent_seen(client, 3600)
    assert _evaluate(client) == 1

    firing = client.get("/api/alerts", params={"state": "firing"}, headers=headers).json()
    assert firing["total"] == 1
    alert = firing["items"][0]
    assert alert["type"] == "agent_offline"
    assert alert["severity"] == "warn"
    assert alert["resource_id"] == "agent_test"
    assert alert["value"].endswith("min")
    assert alert["status"] == "firing"

    notifications = _notifications(client, headers)
    assert len(notifications) == 1
    assert notifications[0]["detail"]["ok"] is True
    assert notifications[0]["detail"]["attempts"] == 1

    acked = client.post(f"/api/alerts/{alert['alert_id']}/ack", headers=headers)
    assert acked.status_code == 200, acked.text
    assert acked.json()["status"] == "acked"
    assert acked.json()["acked_by"]
    # 幂等确认
    assert client.post(
        f"/api/alerts/{alert['alert_id']}/ack", headers=headers
    ).json()["status"] == "acked"

    # 持续 firing 不新建告警、不重复通知
    assert _evaluate(client) == 0
    assert client.get("/api/alerts", headers=headers).json()["total"] == 1
    assert len(_notifications(client, headers)) == 1

    # 恢复：自动 resolved，且不发恢复通知
    _set_agent_seen(client, 0)
    assert _evaluate(client) == 0
    resolved = client.get("/api/alerts", params={"state": "resolved"}, headers=headers).json()
    assert resolved["total"] == 1
    assert resolved["items"][0]["resolved_at"]
    assert len(_notifications(client, headers)) == 1

    # 已恢复不可确认
    assert client.post(
        f"/api/alerts/{alert['alert_id']}/ack", headers=headers
    ).status_code == 409

    # 再次进入 firing：新建告警，但冷却期内不通知
    _set_agent_seen(client, 3600)
    assert _evaluate(client) == 1
    assert client.get("/api/alerts", params={"state": "firing"}, headers=headers).json()[
        "total"
    ] == 1
    assert len(_notifications(client, headers)) == 1

    tested = client.post(f"/api/alert-rules/{rule['rule_id']}/test", headers=headers)
    assert tested.status_code == 200, tested.text
    assert tested.json()["ok"] is True

    patched = client.patch(
        f"/api/alert-rules/{rule['rule_id']}", json={"enabled": False}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["enabled"] is False
    assert client.delete(
        f"/api/alert-rules/{rule['rule_id']}", headers=headers
    ).status_code == 204
    assert client.get("/api/alert-rules", headers=headers).json()["total"] == 0


def test_alert_rule_validation_and_test_send_failure(client):
    headers = _bootstrap(client)
    invalid = client.post(
        "/api/alert-rules",
        json={"name": "未知", "alert_type": "nope", "channel": "inapp"},
        headers=headers,
    )
    assert invalid.status_code == 422

    rule = _rule(
        client, headers, name="Webhook 失败", channel="webhook",
        target="http://127.0.0.1:9/unreachable",
    )
    tested = client.post(f"/api/alert-rules/{rule['rule_id']}/test", headers=headers)
    assert tested.status_code == 200, tested.text
    assert tested.json()["ok"] is False
    assert "失败" in tested.json()["message_zh"]

    audits = client.get(
        "/api/audit", params={"action": "alert_rule.tested"}, headers=headers
    ).json()
    assert audits["total"] == 1
    assert audits["items"][0]["detail"]["attempts"] == 3
    assert audits["items"][0]["detail"]["ok"] is False

    assert client.patch(
        "/api/alert-rules/alr_missing", json={"name": "x"}, headers=headers
    ).status_code == 404
    assert client.delete("/api/alert-rules/alr_missing", headers=headers).status_code == 404
    assert client.post(
        "/api/alerts/alert_missing/ack", headers=headers
    ).status_code == 404

    assert client.get("/api/alerts").status_code == 401
    assert client.get("/api/audit").status_code == 401


def test_audit_filters_detail_diff_and_csv(client):
    headers = _bootstrap(client)
    container = client.app.state.container
    with container.uow() as uow:
        uow.audit.record("emp_root", "test.change", "thing:1", {
            "before": {"a": 1, "b": 1}, "after": {"a": 2, "c": 3}, "note": "x",
        })
        uow.commit()

    listed = client.get("/api/audit", params={"action": "test.change"}, headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    entry = listed.json()["items"][0]
    assert entry["resource"] == "thing:1"
    assert entry["detail"]["note"] == "x"
    assert "diff" not in entry["detail"]

    detail = client.get(f"/api/audit/{entry['audit_id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    diff = {item["field"]: item for item in detail.json()["detail"]["diff"]}
    assert diff["a"] == {"field": "a", "before": 1, "after": 2}
    assert diff["b"]["after"] is None
    assert diff["c"]["before"] is None

    assert client.get(
        "/api/audit", params={"action": "test.change", "actor": "nobody"}, headers=headers
    ).json()["total"] == 0

    exported = client.get(
        "/api/audit", params={"action": "test.change", "format": "csv"}, headers=headers
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "audit_id" in exported.text
    assert "test.change" in exported.text

    assert client.get("/api/audit/999999", headers=headers).status_code == 404
