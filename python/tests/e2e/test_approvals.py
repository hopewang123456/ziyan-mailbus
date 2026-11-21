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


def _create_user_token(client: TestClient, admin: dict[str, str]) -> str:
    invite = client.post(
        "/api/identity/invites",
        json={"account_type": "human", "capabilities": []},
        headers=admin,
    ).json()
    applied = client.post(
        "/api/identity/staff",
        json={
            "display_name": "路人",
            "account_type": "human",
            "invite_code": invite["invite_code"],
        },
    ).json()
    return applied["token"]


def test_approvals_are_scoped_to_data_scope(tmp_path):
    """M11：非全局账号看不到他人发起或归属的审批。"""
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        task_id = _running_task(client, admin)
        approval = _request(client, admin, task_id, "advisory")

        other = _headers(_create_user_token(client, admin))
        assert client.get("/api/approvals", headers=other).json() == []
        assert (
            client.get(
                f"/api/approvals/{approval['approval_id']}", headers=other
            ).status_code
            == 404
        )

        listed = client.get("/api/approvals", headers=admin).json()
        assert any(a["approval_id"] == approval["approval_id"] for a in listed)


def test_manager_cannot_resolve_own_requested_approval(tmp_path):
    """M15：同时持有 hitl_request + hitl_resolve 的非超管不得自审。"""
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        invite = client.post(
            "/api/identity/invites",
            json={
                "account_type": "human",
                "capabilities": [
                    "hitl_request",
                    "hitl_resolve",
                    "task_create",
                    "task_dispatch",
                ],
            },
            headers=admin,
        ).json()
        applied = client.post(
            "/api/identity/staff",
            json={
                "display_name": "自审经理",
                "account_type": "human",
                "invite_code": invite["invite_code"],
            },
        ).json()
        manager = _headers(applied["token"])

        task = client.post("/api/tasks", json={"title": "自审任务"}, headers=manager)
        task_id = task.json()["task_id"]
        client.post(f"/api/tasks/{task_id}/dispatch", headers=manager)
        client.post(
            f"/api/tasks/{task_id}/advance",
            json={"outcome": "running"},
            headers=manager,
        )

        approval = _request(client, manager, task_id, "advisory")

        denied = client.post(
            f"/api/approvals/{approval['approval_id']}/resolve",
            json={"approved": True},
            headers=manager,
        )
        assert denied.status_code == 403, denied.text

        # 超管（ALL）裁决同一审批不受自审规则限制
        resolved = client.post(
            f"/api/approvals/{approval['approval_id']}/resolve",
            json={"approved": True},
            headers=admin,
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "approved"


def test_withdraw_pending_approval_restores_task(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        task_id = _running_task(client, headers)
        approval = _request(client, headers, task_id, "blocking")
        blocked = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        assert blocked["state"] == "blocked"

        invite = client.post(
            "/api/identity/invites",
            json={"account_type": "human", "capabilities": ["hitl_request"]},
            headers=headers,
        ).json()
        applicant = client.post(
            "/api/identity/staff",
            json={
                "display_name": "同僚",
                "account_type": "human",
                "invite_code": invite["invite_code"],
            },
        ).json()
        denied = client.delete(
            f"/api/approvals/{approval['approval_id']}",
            headers=_headers(applicant["token"]),
        )
        assert denied.status_code == 403

        withdrawn = client.delete(
            f"/api/approvals/{approval['approval_id']}", headers=headers
        )
        assert withdrawn.status_code == 204
        resumed = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        assert resumed["state"] == "running"
        detail = client.get(
            f"/api/approvals/{approval['approval_id']}", headers=headers
        ).json()
        assert detail["status"] == "withdrawn"

        assert (
            client.post(
                f"/api/approvals/{approval['approval_id']}/resolve",
                json={"approved": True},
                headers=headers,
            ).status_code
            == 409
        )
        assert (
            client.delete(
                f"/api/approvals/{approval['approval_id']}", headers=headers
            ).status_code
            == 409
        )
        assert (
            client.delete("/api/approvals/appr_missing", headers=headers).status_code
            == 404
        )
