"""B3 端到端：版本发布不影响运行中任务；自由任务与流程任务同一对象。"""

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


def _workflow(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/workflows", json={"name": "内容生产"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["workflow_id"]


def _version(
    client: TestClient, headers: dict[str, str], workflow_id: str, names: list[str]
) -> dict:
    response = client.post(
        f"/api/workflows/{workflow_id}/versions",
        json={"nodes": [{"name": name} for name in names]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _publish(
    client: TestClient, headers: dict[str, str], workflow_id: str, version: int
) -> dict:
    response = client.post(
        f"/api/workflows/{workflow_id}/versions/{version}/publish", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_task(
    client: TestClient, headers: dict[str, str], **payload
) -> dict:
    response = client.post("/api/tasks", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _advance(
    client: TestClient,
    headers: dict[str, str],
    task_id: str,
    outcome: str,
    node_id: str | None = None,
) -> dict:
    body: dict[str, object] = {"outcome": outcome}
    if node_id is not None:
        body["node_id"] = node_id
    response = client.post(
        f"/api/tasks/{task_id}/advance", json=body, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_publishing_new_version_keeps_running_task_on_old_version(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        workflow_id = _workflow(client, headers)

        first = _version(client, headers, workflow_id, ["调研", "撰写"])
        assert first["state"] == "draft"
        assert _publish(client, headers, workflow_id, 1)["state"] == "published"

        task = _create_task(
            client, headers, title="季度报告", workflow_id=workflow_id
        )
        assert task["workflow_version"] == 1
        assert [node["name"] for node in task["nodes"]] == ["调研", "撰写"]

        task_id = task["task_id"]
        dispatched = client.post(
            f"/api/tasks/{task_id}/dispatch", headers=headers
        ).json()
        assert dispatched["state"] == "queued"
        assert dispatched["nodes"][0]["state"] == "dispatched"

        node_one = dispatched["nodes"][0]["node_id"]
        running = _advance(client, headers, task_id, "running", node_one)
        assert running["state"] == "running"
        assert running["nodes"][0]["state"] == "running"

        # 新版本发布后，运行中任务仍锁定旧版本与旧节点
        _version(client, headers, workflow_id, ["一次性完成"])
        _publish(client, headers, workflow_id, 2)

        still = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        assert still["workflow_version"] == 1
        assert [node["name"] for node in still["nodes"]] == ["调研", "撰写"]
        assert still["nodes"][0]["state"] == "running"

        after_first = _advance(client, headers, task_id, "done", node_one)
        assert after_first["nodes"][1]["state"] == "dispatched"
        done = _advance(
            client, headers, task_id, "done", after_first["nodes"][1]["node_id"]
        )
        assert done["state"] == "done"

        # 新建任务默认使用最新发布版本
        latest = _create_task(
            client, headers, title="新报告", workflow_id=workflow_id
        )
        assert latest["workflow_version"] == 2
        assert [node["name"] for node in latest["nodes"]] == ["一次性完成"]


def test_free_task_uses_same_shape_and_advances_without_nodes(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))

        task = _create_task(client, headers, title="临时排查")
        assert task["workflow_id"] is None
        assert task["workflow_version"] is None
        assert task["nodes"] == []
        assert task["state"] == "draft"

        task_id = task["task_id"]
        queued = client.post(f"/api/tasks/{task_id}/dispatch", headers=headers).json()
        assert queued["state"] == "queued"

        running = _advance(client, headers, task_id, "running")
        assert running["state"] == "running"
        assert running["nodes"] == []

        done = _advance(client, headers, task_id, "done")
        assert done["state"] == "done"
        assert set(done) == set(task)


def test_workflow_rename_delete_and_version_detail(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        workflow_id = _workflow(client, headers)
        _version(client, headers, workflow_id, ["调研", "撰写"])
        _publish(client, headers, workflow_id, 1)

        detail = client.get(
            f"/api/workflows/{workflow_id}/versions/1", headers=headers
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["state"] == "published"
        assert [node["name"] for node in detail.json()["nodes"]] == ["调研", "撰写"]

        renamed = client.patch(
            f"/api/workflows/{workflow_id}",
            json={"name": "内容生产（新）"},
            headers=headers,
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "内容生产（新）"
        assert (
            client.get(f"/api/workflows/{workflow_id}", headers=headers).json()["name"]
            == "内容生产（新）"
        )

        deleted = client.delete(f"/api/workflows/{workflow_id}", headers=headers)
        assert deleted.status_code == 204
        assert (
            client.get(f"/api/workflows/{workflow_id}", headers=headers).status_code
            == 404
        )
        assert client.get("/api/workflows", headers=headers).json() == []


def test_workflow_with_tasks_cannot_be_deleted(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        workflow_id = _workflow(client, headers)
        _version(client, headers, workflow_id, ["执行"])
        _publish(client, headers, workflow_id, 1)
        _create_task(client, headers, title="引用任务", workflow_id=workflow_id)

        blocked = client.delete(f"/api/workflows/{workflow_id}", headers=headers)
        assert blocked.status_code == 409
        assert (
            client.get(f"/api/workflows/{workflow_id}", headers=headers).status_code
            == 200
        )


def test_task_writes_require_capability(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))

        staff = client.post(
            "/api/identity/staff",
            json={"display_name": "只读员工", "account_type": "human"},
        )
        assert staff.status_code == 201, staff.text
        employee_id = staff.json()["employee"]["employee_id"]
        client.post(
            f"/api/identity/staff/{employee_id}/review",
            json={"approved": True},
            headers=headers,
        )
        token = client.post(
            f"/api/identity/staff/{employee_id}/activate", headers=headers
        ).json()["token"]

        denied = client.post(
            "/api/tasks", json={"title": "越权任务"}, headers=_headers(token)
        )
        assert denied.status_code == 403
        assert client.get("/api/tasks", headers=_headers(token)).status_code == 200
