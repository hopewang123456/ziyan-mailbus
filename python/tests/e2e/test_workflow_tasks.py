"""B4 端到端：版本隔离、自由任务、任务事件、公开详情、软删除与取消权限。"""

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


def _publish(client: TestClient, headers: dict[str, str], workflow_id: str, version: int):
    response = client.post(
        f"/api/workflows/{workflow_id}/versions/{version}/publish", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _node(
    node_id: str, node_type: str, seq: int, position_id: str | None = None,
    name: str | None = None,
) -> dict:
    return {
        "node_id": node_id,
        "name": name or node_id,
        "node_type": node_type,
        "position_id": position_id,
        "seq": seq,
        "prompt_template": None,
        "needs_artifacts_from": [],
        "max_retries": 1,
        "max_loops": 2,
        "timeout_seconds": None,
        "config": {},
        "pos_x": seq * 120,
        "pos_y": 0,
    }


def _edge(source: str, target: str) -> dict:
    return {"from_node_id": source, "to_node_id": target, "condition": None}


def _create_task(client: TestClient, headers: dict[str, str], **payload) -> dict:
    response = client.post("/api/tasks", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _graph_workflow(client: TestClient, headers: dict[str, str], names: list[str]) -> str:
    position = client.post("/api/positions", json={"name": "执行岗"}, headers=headers)
    assert position.status_code == 201, position.text
    position_id = position.json()["position_id"]
    nodes = [_node("start", "start", 0)]
    nodes += [_node(f"n{index + 1}", "human", index + 1, position_id, name)
              for index, name in enumerate(names)]
    nodes.append(_node("final", "final_approval", len(nodes), position_id, "终验"))
    edges = [_edge(nodes[index]["node_id"], nodes[index + 1]["node_id"])
             for index in range(len(nodes) - 1)]
    created = client.post(
        "/api/workflows",
        json={"name": "人工流程", "graph": {"nodes": nodes, "edges": edges}},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    workflow_id = created.json()["workflow_id"]
    _publish(client, headers, workflow_id, 1)
    return workflow_id


def test_publishing_new_version_keeps_running_task_on_old_version(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        workflow_id = _workflow(client, headers)

        _version(client, headers, workflow_id, ["调研", "撰写"])
        _publish(client, headers, workflow_id, 1)

        task = _create_task(client, headers, title="季度报告", workflow_id=workflow_id)
        assert task["workflow_version"] == 1
        assert [node["name"] for node in task["nodes"]] == ["开始", "调研", "撰写"]
        assert task["state"] == "running"

        # 新版本发布后，运行中任务仍锁定旧版本与旧节点
        _version(client, headers, workflow_id, ["一次性完成"])
        _publish(client, headers, workflow_id, 2)

        still = client.get(f"/api/tasks/{task['task_id']}", headers=headers).json()
        assert still["workflow_version"] == 1
        assert [node["name"] for node in still["nodes"]] == ["开始", "调研", "撰写"]

        latest = _create_task(client, headers, title="新报告", workflow_id=workflow_id)
        assert latest["workflow_version"] == 2
        assert [node["name"] for node in latest["nodes"]] == ["开始", "一次性完成"]


def test_free_task_uses_virtual_node_and_completes(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        task = _create_task(client, headers, title="临时排查")
        assert task["workflow_id"] is None
        assert task["workflow_version"] is None
        assert task["state"] == "running"
        assert [node["node_id"] for node in task["nodes"]] == ["free"]

        done = client.post(
            f"/api/tasks/{task['task_id']}/nodes/free/result",
            json={"attempt_no": 1, "result": "已处理"},
            headers=headers,
        )
        assert done.status_code == 200, done.text
        assert done.json()["state"] == "done"

        cancelled = client.post(
            f"/api/tasks/{task['task_id']}/cancel",
            json={"reason": "manual"},
            headers=headers,
        )
        assert cancelled.status_code == 409


def test_task_updated_event_is_public_safe(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        captured: list[tuple[str, dict]] = []

        class _SpyBus:
            def publish(self, kind: str, payload: dict) -> None:
                captured.append((kind, payload))

        client.app.state.container.task_engine._events = _SpyBus()

        task = _create_task(client, headers, title="季度报告")
        task_id = task["task_id"]
        client.post(
            f"/api/tasks/{task_id}/nodes/free/result",
            json={"attempt_no": 1, "result": "完成"},
            headers=headers,
        )

        events = [payload for kind, payload in captured if kind == "task.updated"]
        assert len(events) == 2
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
        assert events[0]["state"] == "running"
        assert events[0]["progress_total"] == 1
        assert events[1]["state"] == "done"
        assert events[1]["progress_done"] == 1


def test_public_task_detail_exposes_nodes_without_internals(tmp_path):
    with _client(tmp_path) as client:
        session = client.post(
            "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
        )
        assert session.status_code == 201, session.text
        headers = _headers(session.json()["token"])
        workflow_id = _graph_workflow(client, headers, ["调研", "撰写"])
        task = _create_task(client, headers, title="公开节点", workflow_id=workflow_id)
        task_id = task["task_id"]

        # 契约：公开任务详情无需 owner_id，task_id 不可猜测时即安全
        detail = client.get(f"/api/public/collab/tasks/{task_id}")
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert set(body) == {
            "task_id", "title", "state", "created_at", "updated_at", "nodes",
        }
        assert [node["name"] for node in body["nodes"]] == ["start", "调研", "撰写", "终验"]
        for node in body["nodes"]:
            assert set(node) == {"name", "order", "state"}
        assert "created_by" not in body
        assert "owner_id" not in body

        wrong = client.get(
            f"/api/public/collab/tasks/{task_id}", params={"owner_id": "emp_bogus"}
        )
        assert wrong.status_code == 404

        missing = client.get("/api/public/collab/tasks/task_missing")
        assert missing.status_code == 404


def test_workflow_rename_delete_and_published_version(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        workflow_id = _workflow(client, headers)
        _version(client, headers, workflow_id, ["调研", "撰写"])
        _publish(client, headers, workflow_id, 1)

        versions = client.get(
            f"/api/workflows/{workflow_id}/versions", headers=headers
        )
        assert versions.status_code == 200, versions.text
        published = next(
            v for v in versions.json()["items"] if v["version"] == 1
        )
        assert published["state"] == "published"
        assert published["revision"] == 1

        renamed = client.patch(
            f"/api/workflows/{workflow_id}",
            json={"name": "内容生产（新）"},
            headers=headers,
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "内容生产（新）"

        deleted = client.delete(f"/api/workflows/{workflow_id}", headers=headers)
        assert deleted.status_code == 204
        assert (
            client.get(f"/api/workflows/{workflow_id}", headers=headers).status_code
            == 404
        )
        assert client.get("/api/workflows", headers=headers).json()["items"] == []


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

        invite = client.post(
            "/api/employees/invite",
            json={"display_name": "只读员工"},
            headers=headers,
        )
        assert invite.status_code in (200, 201), invite.text
        token = client.post(
            "/api/invites/accept",
            json={"invite_code": invite.json()["invite_code"]},
        ).json()["token"]

        denied = client.post(
            "/api/tasks", json={"title": "越权任务"}, headers=_headers(token)
        )
        assert denied.status_code == 403
        assert client.get("/api/tasks", headers=_headers(token)).status_code == 200


def _scoped_staff(
    client: TestClient, headers: dict[str, str], capabilities: list[str]
) -> dict[str, str]:
    """用邀请创建指定能力、self 范围的已激活员工。"""
    invite = client.post(
        "/api/employees/invite",
        json={
            "display_name": "范围员工",
            "permissions": capabilities,
            "data_scope": "self",
        },
        headers=headers,
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"]},
    )
    assert accepted.status_code == 201, accepted.text
    return _headers(accepted.json()["token"])


def test_task_cancel_is_scoped_and_terminal(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        workflow_id = _graph_workflow(client, headers, ["收集"])
        task_id = _create_task(
            client, headers, title="待取消", workflow_id=workflow_id
        )["task_id"]

        assert client.post(f"/api/tasks/{task_id}/cancel",
                           json={"reason": "manual"}).status_code == 401
        assert (
            client.post(
                "/api/tasks/task_missing/cancel",
                json={"reason": "manual"},
                headers=headers,
            ).status_code
            == 404
        )
        for capabilities in ([], ["task_dispatch"]):
            denied = client.post(
                f"/api/tasks/{task_id}/cancel",
                json={"reason": "manual"},
                headers=_scoped_staff(client, headers, capabilities),
            )
            assert denied.status_code == 403, denied.text

        cancelled = client.post(
            f"/api/tasks/{task_id}/cancel",
            json={"reason": "manual"},
            headers=headers,
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["state"] == "cancelled"
        assert cancelled.json()["termination_reason"] == "manual"
        assert {node["state"] for node in cancelled.json()["nodes"]} <= {
            "done", "skipped",
        }

        again = client.post(
            f"/api/tasks/{task_id}/cancel",
            json={"reason": "manual"},
            headers=headers,
        )
        assert again.status_code == 409

        done_id = _create_task(client, headers, title="已完成")["task_id"]
        client.post(
            f"/api/tasks/{done_id}/nodes/free/result",
            json={"attempt_no": 1, "result": "完成"},
            headers=headers,
        )
        settled = client.post(
            f"/api/tasks/{done_id}/cancel",
            json={"reason": "manual"},
            headers=headers,
        )
        assert settled.status_code == 409
