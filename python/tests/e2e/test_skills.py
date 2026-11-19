"""B4 端到端：技能包登记、探测与 Agent/员工绑定解析。"""

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


def _agent(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/agents",
        json={"name": "研究员", "framework": "claude"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["agent_id"]


def _employee(
    client: TestClient, headers: dict[str, str], agent_id: str
) -> str:
    applied = client.post(
        "/api/identity/staff",
        json={"display_name": "执行者", "account_type": "human", "agent_id": agent_id},
    )
    employee_id = applied.json()["employee"]["employee_id"]
    client.post(
        f"/api/identity/staff/{employee_id}/review",
        json={"approved": True},
        headers=headers,
    )
    client.post(f"/api/identity/staff/{employee_id}/activate", headers=headers)
    return employee_id


def _skill_dir(tmp_path, version: str = "1.2.3"):
    path = tmp_path / "vault" / "research"
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: research\nversion: {version}\n---\n", encoding="utf-8"
    )
    return path


def test_skill_package_refresh_and_bindings(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client))
        agent_id = _agent(client, admin_headers)
        employee_id = _employee(client, admin_headers, agent_id)
        skill_dir = _skill_dir(tmp_path)

        created = client.post(
            "/api/skills",
            json={
                "name": "研究工作流技能",
                "source_type": "local",
                "source_uri": str(skill_dir),
                "note": "Obsidian vault",
            },
            headers=admin_headers,
        )
        assert created.status_code == 201, created.text
        package = created.json()
        package_id = package["package_id"]
        assert package["entry"] == "SKILL.md"
        assert package["version"] == ""
        assert package["bindings"] == []

        refreshed = client.post(
            f"/api/skills/{package_id}/refresh", headers=admin_headers
        )
        assert refreshed.status_code == 200, refreshed.text
        body = refreshed.json()
        assert body["version"] == "1.2.3"
        assert body["last_error"] is None
        assert body["last_checked_at"] is not None

        # 来源变更后探测结果立即失效
        moved = client.patch(
            f"/api/skills/{package_id}",
            json={"source_uri": str(tmp_path / "missing")},
            headers=admin_headers,
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["version"] == ""
        failed = client.post(
            f"/api/skills/{package_id}/refresh", headers=admin_headers
        )
        assert failed.json()["last_error"]
        assert failed.json()["version"] == ""

        client.patch(
            f"/api/skills/{package_id}",
            json={"source_uri": str(skill_dir)},
            headers=admin_headers,
        )
        client.post(f"/api/skills/{package_id}/refresh", headers=admin_headers)

        bound = client.post(
            f"/api/skills/{package_id}/bindings",
            json={"target_type": "agent", "target_id": agent_id},
            headers=admin_headers,
        )
        assert bound.status_code == 200, bound.text
        assert bound.json()["bindings"] == [
            {"target_type": "agent", "target_id": agent_id, "enabled": True}
        ]

        inherited = client.get(
            "/api/skills/effective",
            params={"target_type": "employee", "target_id": employee_id},
            headers=admin_headers,
        )
        assert inherited.status_code == 200, inherited.text
        assert [item["origin"] for item in inherited.json()] == ["agent"]
        assert inherited.json()[0]["enabled"] is True

        overridden = client.post(
            f"/api/skills/{package_id}/bindings",
            json={
                "target_type": "employee",
                "target_id": employee_id,
                "enabled": False,
            },
            headers=admin_headers,
        )
        assert overridden.status_code == 200, overridden.text
        effective = client.get(
            "/api/skills/effective",
            params={"target_type": "employee", "target_id": employee_id},
            headers=admin_headers,
        ).json()
        assert effective[0]["origin"] == "employee"
        assert effective[0]["enabled"] is False

        deleted = client.post(
            f"/api/skills/{package_id}/delete", headers=admin_headers
        )
        assert deleted.status_code == 204
        assert client.get("/api/skills", headers=admin_headers).json() == []
        assert (
            client.get(
                "/api/skills/effective",
                params={"target_type": "employee", "target_id": employee_id},
                headers=admin_headers,
            ).json()
            == []
        )


def test_skill_write_requires_system_config(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client))
        applied = client.post(
            "/api/identity/staff", json={"display_name": "小王", "account_type": "human"}
        )
        employee_id = applied.json()["employee"]["employee_id"]
        client.post(
            f"/api/identity/staff/{employee_id}/review",
            json={"approved": True},
            headers=admin_headers,
        )
        token = client.post(
            f"/api/identity/staff/{employee_id}/activate", headers=admin_headers
        ).json()["token"]
        denied = client.post(
            "/api/skills",
            json={"name": "越权", "source_type": "local", "source_uri": "x"},
            headers=_headers(token),
        )
        assert denied.status_code == 403
