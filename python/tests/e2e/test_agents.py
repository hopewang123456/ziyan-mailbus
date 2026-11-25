"""B3 端到端：Agent 台账、员工绑定与布局执行态投影。"""

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


def _hire(
    client: TestClient, headers: dict[str, str], name: str
) -> tuple[str, str]:
    invite = client.post(
        "/api/employees/invite", json={"display_name": name}, headers=headers
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"], "display_name": name},
    )
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()
    return body["employee"]["employee_id"], body["token"]


def _position(
    client: TestClient, headers: dict[str, str], name: str = "研究岗"
) -> str:
    response = client.post("/api/positions", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["position_id"]


def _create_agent(
    client: TestClient,
    headers: dict[str, str],
    name: str = "研究员",
    framework: str = "claude",
    model: str = "deepseek-v4",
    endpoint: str | None = None,
    position_id: str | None = None,
) -> dict:
    if position_id is None:
        position_id = _position(client, headers)
    invite = client.post(
        "/api/agent-invites",
        json={"employee_name": name, "position_id": position_id},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    payload: dict = {"invite_code": invite.json()["invite_code"], "name": name}
    payload["framework"] = framework
    payload["model"] = model
    if endpoint is not None:
        payload["endpoint"] = endpoint
    registered = client.post("/api/agents/register", json=payload)
    assert registered.status_code == 201, registered.text
    return {"position_id": position_id, "invite": invite.json(), **registered.json()}


def _seat_ids(client: TestClient, headers: dict[str, str]) -> list[str]:
    layout = client.get("/api/layout", headers=headers).json()
    return [
        seat["seat_id"]
        for floor in layout["floors"]
        for room in floor["rooms"]
        for seat in room["seats"]
    ]


def _assign_seat(client, headers, seat_id: str, employee_id: str):
    return client.put(
        f"/api/seats/{seat_id}/assign",
        json={"employee_id": employee_id},
        headers=headers,
    )


def _running_task(
    client: TestClient, headers: dict[str, str], owner_id: str
) -> dict:
    position = client.post("/api/positions", json={"name": "研究岗"}, headers=headers)
    assert position.status_code == 201, position.text
    position_id = position.json()["position_id"]
    graph = {
        "nodes": [
            _graph_node("start", "start", 0),
            _graph_node("collect", "human", 1, position_id, "收集"),
            _graph_node("execute", "human", 2, position_id, "执行"),
            _graph_node("final", "final_approval", 3, position_id, "终验"),
        ],
        "edges": [
            {"from_node_id": "start", "to_node_id": "collect", "condition": None},
            {"from_node_id": "collect", "to_node_id": "execute", "condition": None},
            {"from_node_id": "execute", "to_node_id": "final", "condition": None},
        ],
    }
    workflow = client.post(
        "/api/workflows",
        json={"name": "研究工作流", "graph": graph},
        headers=headers,
    )
    assert workflow.status_code == 201, workflow.text
    workflow_id = workflow.json()["workflow_id"]
    published = client.post(
        f"/api/workflows/{workflow_id}/versions/1/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    task = client.post(
        "/api/tasks",
        json={"title": "季度研究", "owner_id": owner_id, "workflow_id": workflow_id},
        headers=headers,
    )
    assert task.status_code == 201, task.text
    return task.json()


def _graph_node(
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


def _seat_agent(
    client: TestClient,
    seat_id: str,
    headers: dict[str, str],
    public: bool = False,
) -> dict:
    path = "/api/public/layout" if public else "/api/layout"
    layout = client.get(path, headers=None if public else headers)
    assert layout.status_code == 200, layout.text
    seats = [
        seat
        for floor in layout.json()["floors"]
        for room in floor["rooms"]
        for seat in room["seats"]
    ]
    agent = next(item for item in seats if item["seat_id"] == seat_id)["agent"]
    assert agent is not None
    return agent


def test_agent_ledger_crud_and_permission(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client))
        agent = _create_agent(client, admin_headers)
        assert agent["agent_id"].startswith("agent_")
        assert agent["endpoint_review_status"] == "approved"

        listed = client.get("/api/agents", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        assert agent["agent_id"] in [item["agent_id"] for item in listed.json()["items"]]

        detail = client.get(
            f"/api/agents/{agent['agent_id']}", headers=admin_headers
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["name"] == "研究员"
        assert detail.json()["framework"] == "claude"
        assert detail.json()["enabled"] is True

        # 契约未提供更新端点，沿用仍保留的兼容别名以覆盖名称/启停切换。
        updated = client.patch(
            f"/api/agents/{agent['agent_id']}",
            json={"name": "高级研究员", "enabled": False},
            headers=admin_headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "高级研究员"
        assert updated.json()["enabled"] is False
        assert updated.json()["framework"] == "claude"

        rotated = client.post(
            f"/api/agents/{agent['agent_id']}/rotate-token", headers=admin_headers
        )
        assert rotated.status_code == 200, rotated.text
        assert rotated.json()["token"]
        assert rotated.json()["fingerprint"]

        revoked = client.post(
            f"/api/agents/{agent['agent_id']}/revoke-token", headers=admin_headers
        )
        assert revoked.status_code == 200, revoked.text

        _, token = _hire(client, admin_headers, "小王")
        denied = client.post(
            "/api/agent-invites", json={"employee_name": "越权 Agent"}, headers=_headers(token)
        )
        assert denied.status_code == 403
        assert client.get("/api/agents", headers=_headers(token)).status_code == 403


def test_employee_binding_and_layout_execution(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client))
        agent = _create_agent(
            client, admin_headers, endpoint="http://127.0.0.1:9001"
        )
        seat_id = _seat_ids(client, admin_headers)[0]
        seated = _assign_seat(
            client, admin_headers, seat_id, agent["employee_id"]
        )
        assert seated.status_code == 200, seated.text

        employee = client.get(
            f"/api/employees/{agent['employee_id']}", headers=admin_headers
        ).json()
        assert employee["agent_id"] == agent["agent_id"]
        assert employee["agent_name"] == "研究员"
        assert employee["agent_framework"] == "claude"

        idle = _seat_agent(client, seat_id, admin_headers)
        assert idle["bound_agent_id"] == agent["agent_id"]
        assert idle["agent_name"] == "研究员"
        assert idle["agent_framework"] == "claude"
        assert idle["task_state"] == ""

        _running_task(client, admin_headers, agent["employee_id"])
        busy = _seat_agent(client, seat_id, admin_headers)
        assert busy["status"] == "busy"
        assert busy["task"] == "季度研究"
        assert busy["task_state"] == "running"
        assert busy["progress_total"] == 4

        public = _seat_agent(client, seat_id, admin_headers, public=True)
        assert "agent_id" not in public
        assert "bound_agent_id" not in public
        assert "task_id" not in public
        assert "last_heartbeat" not in public
        assert public["agent_name"] == "研究员"
        assert public["agent_framework"] == "claude"
        assert public["task_state"] == "running"
        assert public["progress_total"] == 4

        # Agent 仍被在职员工绑定，注销必须被阻止。
        blocked = client.delete(
            f"/api/agents/{agent['agent_id']}", headers=admin_headers
        )
        assert blocked.status_code == 409, blocked.text


def test_agent_delete_requires_unbound_employee(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client))
        agent = _create_agent(client, admin_headers)

        blocked = client.delete(f"/api/agents/{agent['agent_id']}", headers=admin_headers)
        assert blocked.status_code == 409, blocked.text

        # 软删除绑定的员工后即可注销 Agent。
        removed = client.delete(
            f"/api/employees/{agent['employee_id']}", headers=admin_headers
        )
        assert removed.status_code == 204, removed.text

        deleted = client.delete(f"/api/agents/{agent['agent_id']}", headers=admin_headers)
        assert deleted.status_code == 204
        assert client.get("/api/agents", headers=admin_headers).json()["items"] == []
        assert (
            client.delete(f"/api/agents/{agent['agent_id']}", headers=admin_headers).status_code
            == 404
        )

        spare = _create_agent(client, admin_headers)
        _, staff_token = _hire(client, admin_headers, "越权者")
        denied = client.delete(
            f"/api/agents/{spare['agent_id']}", headers=_headers(staff_token)
        )
        assert denied.status_code == 403
