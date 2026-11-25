"""B5：Agent 注册、token 安全、endpoint 审批与 A2A 幂等回归。"""

from __future__ import annotations

import json
import sqlite3

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


def _position(client: TestClient, headers, name: str = "Agent 岗") -> str:
    response = client.post("/api/positions", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["position_id"]


def _invite(client: TestClient, headers, position_id: str) -> dict:
    response = client.post(
        "/api/agent-invites",
        json={
            "employee_name": "执行 Agent",
            "position_id": position_id,
            "capabilities": ["ops"],
            "permissions": ["message_send", "result_submit"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _register(client: TestClient, invite_code: str, endpoint: str) -> dict:
    response = client.post(
        "/api/agents/register",
        json={"invite_code": invite_code, "name": "执行 Agent", "endpoint": endpoint},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _a2a(client: TestClient, token: str, payload: dict):
    return client.post(
        "/api/a2a/messages",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def _agent_graph(client: TestClient, headers, position_id: str) -> str:
    nodes = [
        {"node_id": "start", "name": "start", "node_type": "start", "seq": 0,
         "needs_artifacts_from": [], "config": {}, "pos_x": 0, "pos_y": 0},
        {"node_id": "work", "name": "work", "node_type": "agent", "seq": 1,
         "position_id": position_id, "needs_artifacts_from": [], "max_retries": 0,
         "max_loops": 2, "config": {}, "pos_x": 120, "pos_y": 0},
        {"node_id": "final", "name": "final", "node_type": "final_approval", "seq": 2,
         "position_id": position_id, "needs_artifacts_from": [], "config": {},
         "pos_x": 240, "pos_y": 0},
    ]
    edges = [
        {"from_node_id": "start", "to_node_id": "work", "condition": None},
        {"from_node_id": "work", "to_node_id": "final", "condition": None},
    ]
    created = client.post(
        "/api/workflows",
        json={"name": "Agent 流", "graph": {"nodes": nodes, "edges": edges}},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    workflow_id = created.json()["workflow_id"]
    published = client.post(
        f"/api/workflows/{workflow_id}/versions/1/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    return workflow_id


def _start(client: TestClient, headers, workflow_id: str) -> dict:
    response = client.post(
        "/api/tasks", json={"title": "Agent 任务", "workflow_id": workflow_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_token_cipher_and_endpoint_approval(client, tmp_path) -> None:
    headers = _bootstrap(client)
    invite = _invite(client, headers, _position(client, headers))
    registration = _register(client, invite["invite_code"], "http://127.0.0.1:7890/a2a")
    token = registration["token"]
    assert registration["endpoint_review_status"] == "pending"

    listed = client.get("/api/agents", headers=headers)
    assert listed.status_code == 200, listed.text
    agent = listed.json()["items"][0]
    assert agent["endpoint_review_status"] == "pending"
    assert agent["endpoint"] is None
    assert agent["pending_endpoint"] == "http://127.0.0.1:7890/a2a"
    assert token not in listed.text

    with sqlite3.connect(tmp_path / "mailbus.db") as conn:
        stored = conn.execute(
            "SELECT endpoint_token, endpoint_token_lookup_hash FROM agents"
        ).fetchone()
    assert stored[0] and stored[0] != token and stored[0].startswith("enc:")
    assert token not in json.dumps(stored)
    cipher = client.app.state.container.token_cipher
    assert cipher.decrypt(stored[0]) == token
    assert cipher.lookup_digest(token) == stored[1]

    approved = client.post(
        f"/api/agents/{registration['agent_id']}/endpoint/approve", headers=headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["endpoint_review_status"] == "approved"
    assert approved.json()["endpoint"] == "http://127.0.0.1:7890/a2a"


def test_rejects_metadata_endpoint_and_invalid_token(client) -> None:
    headers = _bootstrap(client)
    invite = _invite(client, headers, _position(client, headers))
    rejected = client.post(
        "/api/agents/register",
        json={
            "invite_code": invite["invite_code"],
            "name": "坏 Agent",
            "endpoint": "http://169.254.169.254/latest/meta-data",
        },
    )
    assert rejected.status_code == 422, rejected.text
    assert client.post(
        "/api/a2a/messages",
        json={"type": "heartbeat"},
        headers={"Authorization": "Bearer not-a-real-token"},
    ).status_code == 401


def test_pending_endpoint_blocks_dispatch_and_a2a_result_is_idempotent(client) -> None:
    headers = _bootstrap(client)
    position_id = _position(client, headers)
    invite = _invite(client, headers, position_id)
    registration = _register(client, invite["invite_code"], "http://127.0.0.1:7890/a2a")
    token = registration["token"]
    workflow_id = _agent_graph(client, headers, position_id)

    task = _start(client, headers, workflow_id)
    assert task["runs"] == [], "endpoint 待审批时不得派单"

    approved = client.post(
        f"/api/agents/{registration['agent_id']}/endpoint/approve", headers=headers
    )
    assert approved.status_code == 200, approved.text
    heartbeat = _a2a(
        client, token, {"type": "heartbeat", "endpoint": "http://127.0.0.1:7890/a2a"}
    )
    assert heartbeat.status_code == 201, heartbeat.text

    task = _start(client, headers, workflow_id)
    assert len(task["runs"]) == 1
    run = task["runs"][0]
    assert run["assigned_employee_id"] == registration["employee_id"]

    payload = {
        "type": "result",
        "run_id": run["run_id"],
        "attempt_no": run["attempt_no"],
        "status": "completed",
        "output": "done",
    }
    first = _a2a(client, token, payload)
    assert first.status_code == 201, first.text
    assert first.json()["accepted"] is True
    detail = client.get(f"/api/tasks/{task['task_id']}", headers=headers)
    work_runs = [item for item in detail.json()["runs"] if item["node_id"] == "work"]
    assert work_runs and work_runs[0]["state"] == "done"

    duplicate = _a2a(client, token, payload)
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["duplicate"] is True

    stale = _a2a(client, token, {**payload, "attempt_no": run["attempt_no"] + 1})
    assert stale.status_code == 409, stale.text
    assert stale.json()["error_code"] == "stale_run"

    rotated = client.post(
        f"/api/agents/{registration['agent_id']}/rotate-token", headers=headers
    )
    assert rotated.status_code == 200, rotated.text
    new_token = rotated.json()["token"]
    assert new_token != token
    assert _a2a(client, token, {"type": "heartbeat"}).status_code == 201
    assert _a2a(client, new_token, {"type": "heartbeat"}).status_code == 201

    revoked = client.post(
        f"/api/agents/{registration['agent_id']}/revoke-token", headers=headers
    )
    assert revoked.status_code == 200, revoked.text
    assert _a2a(client, new_token, {"type": "heartbeat"}).status_code == 401
    listed = client.get("/api/agents", headers=headers).json()["items"][0]
    assert listed["online"] is False
