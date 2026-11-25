"""任务列表按登录人隔离：非超管只看与自己相关的任务。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _activate(client: TestClient, admin: dict, name: str) -> tuple[str, str]:
    invite = client.post(
        "/api/employees/invite", json={"display_name": name}, headers=admin
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"], "display_name": name},
    )
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()
    return body["employee"]["employee_id"], body["token"]


def test_task_list_is_scoped_for_regular_staff() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with TestClient(create_app(Settings(data_dir=Path(tmp)))) as client:
            admin = client.post(
                "/api/identity/bootstrap/super-admin", json={"display_name": "超管"}
            ).json()
            admin_headers = _auth(admin["token"])
            employee_id, staff_token = _activate(client, admin_headers, "甲")
            _, other_token = _activate(client, admin_headers, "乙")

            client.post("/api/tasks", json={"title": "给甲的"}, headers=admin_headers)
            client.post(
                "/api/tasks",
                json={"title": "指派甲", "owner_id": employee_id},
                headers=admin_headers,
            )

            def titles(headers: dict, path: str = "/api/tasks") -> set[str]:
                resp = client.get(path, headers=headers)
                assert resp.status_code == 200, resp.text
                return {item["title"] for item in resp.json()["items"]}

            assert titles(admin_headers) == {"给甲的", "指派甲"}
            assert titles(_auth(staff_token)) == {"指派甲"}
            assert titles(_auth(other_token)) == set()

            # 过滤参数白名单：非法状态是请求错误，不应落成领域 409
            bad = client.get("/api/tasks?state=bogus", headers=admin_headers)
            assert bad.status_code == 422, bad.text
