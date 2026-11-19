"""B4 端到端：HITL 三档行为各一条。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path)))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> str:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _running_task(client: TestClient, headers: dict[str, str]) -> str:
    task = client.post("/api/tasks", json={"title": "等待审批"}, headers=headers)
    assert task.status_code == 201, task.text
    task_id = task.json()["task_id"]
    client.post(f"/api/tasks/{task_id}/dispatch", headers=headers)
    client.post(
        f"/api/tasks/{task_id}/advance", json={"outcome": "running"}, headers=headers
    )
    return task_id


def _request(
    client: TestClient, headers: dict[str, str], task_id: str, tier: str
) -> dict:
    response = client.post(
        "/api/approvals",
        json={"task_id": task_id, "title": "请确认", "tier": tier},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_blocking_tier_blocks_task_until_approved(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        task_id = _running_task(client, headers)

        approval = _request(client, headers, task_id, "blocking")
        assert approval["status"] == "pending"
        assert approval["tier"] == "blocking"
        assert approval["expires_at"] is not None

        blocked = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        assert blocked["state"] == "blocked"

        resolved = client.post(
            f"/api/approvals/{approval['approval_id']}/resolve",
            json={"approved": True},
            headers=headers,
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "approved"

        resumed = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        assert resumed["state"] == "running"


def test_advisory_tier_never_blocks_task(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        task_id = _running_task(client, headers)

        approval = _request(client, headers, task_id, "advisory")
        assert approval["status"] == "pending"
        still = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        assert still["state"] == "running"

        rejected = client.post(
            f"/api/approvals/{approval['approval_id']}/resolve",
            json={"approved": False, "note": "仅记录"},
            headers=headers,
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "rejected"

        after = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        assert after["state"] == "running"


def test_informational_tier_is_acknowledged_and_not_resolvable(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        task_id = _running_task(client, headers)

        approval = _request(client, headers, task_id, "informational")
        assert approval["status"] == "acknowledged"
        assert approval["resolved_at"] is not None

        unchanged = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        assert unchanged["state"] == "running"

        denied = client.post(
            f"/api/approvals/{approval['approval_id']}/resolve",
            json={"approved": True},
            headers=headers,
        )
        assert denied.status_code == 409

        pending = client.get(
            f"/api/approvals?task_id={task_id}&status=pending", headers=headers
        )
        assert pending.status_code == 200
        assert pending.json() == []
