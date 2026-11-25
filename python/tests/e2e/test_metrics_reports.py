"""B7：指标概览/趋势/排行/CSV，统一走服务端 data_scope 过滤。"""

from __future__ import annotations

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


def _self_scoped_user(client: TestClient, admin_headers) -> dict[str, str]:
    invite = client.post(
        "/api/employees/invite",
        json={"display_name": "普通员工"},
        headers=admin_headers,
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"]},
    )
    assert accepted.status_code == 201, accepted.text
    return _headers(accepted.json()["token"])


def test_metrics_overview_trend_breakdown_and_scope(client):
    admin = _bootstrap(client)
    for title in ("报表任务一", "报表任务二"):
        created = client.post("/api/tasks", json={"title": title}, headers=admin)
        assert created.status_code == 201, created.text

    overview = client.get("/api/metrics/overview", headers=admin)
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["totals"]["total"] == 2
    cards = {item["metric"]: item for item in body["cards"]}
    assert cards["tasks.total"]["value"] == 2
    assert cards["tasks.completion_rate"]["unit"] == "percent"
    assert "agents.online" in cards
    assert "tasks.backlog" in cards

    trend = client.get(
        "/api/metrics/trend", params={"bucket": "day"}, headers=admin
    )
    assert trend.status_code == 200, trend.text
    series = {item["metric"]: item for item in trend.json()["series"]}
    created_points = series["tasks.created"]["points"]
    assert sum(point["value"] for point in created_points) == 2
    assert series["tasks.completed"]["points"]

    breakdown = client.get(
        "/api/metrics/breakdown", params={"metric": "agent_load"}, headers=admin
    )
    assert breakdown.status_code == 200, breakdown.text
    assert breakdown.json()["metric"] == "agent_load"
    items = breakdown.json()["items"]
    assert len(items) == 1
    assert items[0]["label"] == "超级管理员"
    assert items[0]["value"] == 2
    assert breakdown.json()["extra"][items[0]["key"]]["total"] == 2

    unknown = client.get(
        "/api/metrics/breakdown", params={"metric": "nope"}, headers=admin
    )
    assert unknown.status_code == 422

    future = client.get(
        "/api/metrics/overview", params={"from": "2999-01-01"}, headers=admin
    )
    assert future.status_code == 422  # from 晚于 to

    # self 范围用户看不到他人任务：同一接口按 data_scope 服务端过滤
    scoped = _self_scoped_user(client, admin)
    mine = client.get("/api/metrics/overview", headers=scoped)
    assert mine.status_code == 200, mine.text
    assert mine.json()["totals"]["total"] == 0


def test_metrics_export_csv_uses_same_scope(client):
    admin = _bootstrap(client)
    client.post("/api/tasks", json={"title": "导出任务"}, headers=admin)

    exported = client.get("/api/metrics/export", headers=admin)
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("text/csv")
    assert "attachment" in exported.headers["content-disposition"]
    assert "tasks.total" in exported.text
    assert "section" in exported.text.splitlines()[0]

    scoped = _self_scoped_user(client, admin)
    mine = client.get("/api/metrics/export", headers=scoped)
    assert mine.status_code == 200
    totals = [line for line in mine.text.splitlines() if "tasks.total" in line]
    assert len(totals) == 1
    assert totals[0].endswith(",0,count")
