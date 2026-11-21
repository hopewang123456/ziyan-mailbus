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


def test_task_updated_event_is_public_safe(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        captured: list[tuple[str, dict]] = []

        class _SpyBus:
            def publish(self, kind: str, payload: dict) -> None:
                captured.append((kind, payload))

        client.app.state.container.tasks._events = _SpyBus()

        workflow_id = _workflow(client, headers)
        _version(client, headers, workflow_id, ["调研", "撰写"])
        _publish(client, headers, workflow_id, 1)

        task = _create_task(
            client, headers, title="季度报告", workflow_id=workflow_id
        )
        task_id = task["task_id"]

        dispatched = client.post(
            f"/api/tasks/{task_id}/dispatch", headers=headers
        ).json()
        node_one = dispatched["nodes"][0]["node_id"]
        _advance(client, headers, task_id, "running", node_one)
        _advance(client, headers, task_id, "done", node_one)

        events = [payload for kind, payload in captured if kind == "task.updated"]
        assert len(events) == 4
        assert {event["task_id"] for event in events} == {task_id}
        # 公开大屏只拿展示字段，不暴露负责人/创建者/流程标识
        assert set(events[0]) == {
            "task_id",
            "seat_id",
            "title",
            "state",
            "current_node",
            "node_state",
            "progress_done",
            "progress_total",
            "updated_at",
        }
        assert "owner_id" not in events[0]
        assert events[0]["title"] == "季度报告"
        assert events[1]["state"] == "queued"
        assert events[1]["node_state"] == "dispatched"
        assert events[2]["state"] == "running"
        assert events[2]["node_state"] == "running"
        assert events[3]["progress_done"] == 1
        assert events[3]["progress_total"] == 2
        assert events[3]["current_node"] == "撰写"


def test_public_task_detail_exposes_nodes_without_internals(tmp_path):
    with _client(tmp_path) as client:
        session = client.post(
            "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
        )
        assert session.status_code == 201, session.text
        headers = _headers(session.json()["token"])
        workflow_id = _workflow(client, headers)
        _version(client, headers, workflow_id, ["调研", "撰写"])
        _publish(client, headers, workflow_id, 1)
        task = _create_task(
            client, headers, title="公开节点", workflow_id=workflow_id
        )
        task_id = task["task_id"]

        # 契约：公开任务详情无需 owner_id，task_id 不可猜测时即安全
        detail = client.get(f"/api/public/collab/tasks/{task_id}")
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert set(body) == {
            "task_id",
            "title",
            "state",
            "created_at",
            "updated_at",
            "nodes",
        }
        assert [node["name"] for node in body["nodes"]] == ["调研", "撰写"]
        for node in body["nodes"]:
            assert set(node) == {"name", "order", "state"}
        assert "created_by" not in body
        assert "owner_id" not in body

        # 传了 owner_id 但不匹配 → 404（不泄露任务存在性）
        wrong = client.get(
            f"/api/public/collab/tasks/{task_id}", params={"owner_id": "emp_bogus"}
        )
        assert wrong.status_code == 404

        missing = client.get("/api/public/collab/tasks/task_missing")
        assert missing.status_code == 404


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


def _scoped_staff(
    client: TestClient, headers: dict[str, str], capabilities: list[str]
) -> dict[str, str]:
    """用邀请码创建指定能力、self 范围的已激活员工。"""
    invite = client.post(
        "/api/identity/invites",
        json={
            "account_type": "human",
            "capabilities": capabilities,
            "data_scope": "self",
        },
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    applied = client.post(
        "/api/identity/staff",
        json={
            "display_name": "范围员工",
            "account_type": "human",
            "invite_code": invite.json()["invite_code"],
        },
    )
    assert applied.status_code == 201, applied.text
    return _headers(applied.json()["token"])


def test_task_cancel_is_idempotent_and_scoped(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        workflow_id = _workflow(client, headers)
        _version(client, headers, workflow_id, ["收集", "执行"])
        _publish(client, headers, workflow_id, 1)
        task_id = _create_task(
            client, headers, title="待取消", workflow_id=workflow_id
        )["task_id"]
        client.post(f"/api/tasks/{task_id}/dispatch", headers=headers)
        _advance(client, headers, task_id, "running")

        assert client.post(f"/api/tasks/{task_id}/cancel").status_code == 401
        assert (
            client.post("/api/tasks/task_missing/cancel", headers=headers).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/tasks/{task_id}/cancel",
                headers=_scoped_staff(client, headers, []),
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/tasks/{task_id}/cancel",
                headers=_scoped_staff(client, headers, ["task_dispatch"]),
            ).status_code
            == 403
        )

        cancelled = client.post(f"/api/tasks/{task_id}/cancel", headers=headers)
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["state"] == "cancelled"
        assert {node["state"] for node in cancelled.json()["nodes"]} == {"skipped"}

        again = client.post(f"/api/tasks/{task_id}/cancel", headers=headers)
        assert again.status_code == 200
        assert again.json()["state"] == "cancelled"

        done_id = _create_task(client, headers, title="已完成")["task_id"]
        client.post(f"/api/tasks/{done_id}/dispatch", headers=headers)
        _advance(client, headers, done_id, "running")
        _advance(client, headers, done_id, "done")
        settled = client.post(f"/api/tasks/{done_id}/cancel", headers=headers)
        assert settled.status_code == 200
        assert settled.json()["state"] == "done"
