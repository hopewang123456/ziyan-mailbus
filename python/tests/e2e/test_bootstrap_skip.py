"""引导向导跳过步骤：权限、白名单、幂等与完成态。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path)))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return _headers(response.json()["token"])


def _staff(client: TestClient, headers: dict[str, str]) -> dict[str, str]:
    applied = client.post(
        "/api/identity/staff",
        json={"display_name": "普通员工", "account_type": "human"},
    )
    assert applied.status_code == 201, applied.text
    employee_id = applied.json()["employee"]["employee_id"]
    client.post(
        f"/api/identity/staff/{employee_id}/review",
        json={"approved": True},
        headers=headers,
    )
    token = client.post(
        f"/api/identity/staff/{employee_id}/activate", headers=headers
    ).json()["token"]
    return _headers(token)


def test_skip_requires_admin_and_respects_step_whitelist(tmp_path):
    with _client(tmp_path) as client:
        headers = _bootstrap(client)

        assert (
            client.post("/api/identity/bootstrap/model_config/skip").status_code == 401
        )
        denied = client.post(
            "/api/identity/bootstrap/model_config/skip",
            headers=_staff(client, headers),
        )
        assert denied.status_code == 403

        refused = client.post(
            "/api/identity/bootstrap/super_admin/skip", headers=headers
        )
        assert refused.status_code == 409
        assert "不可跳过" in refused.json()["message_zh"]

        unknown = client.post("/api/identity/bootstrap/bogus/skip", headers=headers)
        assert unknown.status_code == 409


def test_skip_marks_steps_done_and_completes_wizard(tmp_path):
    with _client(tmp_path) as client:
        headers = _bootstrap(client)

        first = client.post(
            "/api/identity/bootstrap/model_config/skip", headers=headers
        )
        assert first.status_code == 200, first.text
        assert first.json()["completed"] is False
        steps = {step["step"]: step for step in first.json()["steps"]}
        assert steps["model_config"]["done"] is True

        repeat = client.post(
            "/api/identity/bootstrap/model_config/skip", headers=headers
        )
        assert repeat.status_code == 200
        assert repeat.json()["completed"] is False

        second = client.post(
            "/api/identity/bootstrap/first_team/skip", headers=headers
        )
        assert second.status_code == 200, second.text
        assert second.json()["completed"] is True
