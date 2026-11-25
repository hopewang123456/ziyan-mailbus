"""B4 任务域端到端：自由任务、CAS 认领、结果 attempt、取消、终验与重跑。"""

from __future__ import annotations

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


def _node(node_id: str, node_type: str, seq: int, config: dict | None = None,
          position_id: str | None = None, max_retries: int = 1) -> dict:
    return {
        "node_id": node_id,
        "name": node_id,
        "node_type": node_type,
        "position_id": position_id,
        "seq": seq,
        "prompt_template": None,
        "needs_artifacts_from": [],
        "max_retries": max_retries,
        "max_loops": 2,
        "timeout_seconds": None,
        "config": config or {},
        "pos_x": seq * 120,
        "pos_y": 0,
    }


def _edge(source: str, target: str) -> dict:
    return {"from_node_id": source, "to_node_id": target, "condition": None}


def _published(client: TestClient, headers, nodes: list[dict], edges: list[dict]) -> str:
    created = client.post(
        "/api/workflows",
        json={"name": "任务流", "graph": {"nodes": nodes, "edges": edges}},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    workflow_id = created.json()["workflow_id"]
    published = client.post(
        f"/api/workflows/{workflow_id}/versions/1/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    return workflow_id


def _start_task(client: TestClient, headers, workflow_id: str, title: str = "任务") -> dict:
    created = client.post(
        "/api/tasks", json={"title": title, "workflow_id": workflow_id}, headers=headers
    )
    assert created.status_code == 201, created.text
    return created.json()


def _human_graph(client: TestClient, headers) -> str:
    position = client.post("/api/positions", json={"name": "执行岗"}, headers=headers)
    assert position.status_code == 201, position.text
    position_id = position.json()["position_id"]
    nodes = [_node("start", "start", 0),
             _node("work", "human", 1, position_id=position_id),
             _node("final", "final_approval", 2, position_id=position_id)]
    edges = [_edge("start", "work"), _edge("work", "final")]
    return _published(client, headers, nodes, edges)


def test_free_task_starts_immediately_and_completes_on_result(client) -> None:
    headers = _bootstrap(client)
    created = client.post("/api/tasks", json={"title": "临时排查"}, headers=headers)
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["state"] == "running"
    assert task["workflow_id"] is None
    assert [node["node_id"] for node in task["nodes"]] == ["free"]
    run = task["nodes"][0]["runs"][0]
    assert run["attempt_no"] == 1
    assert run["assigned_employee_id"] == task["owner_id"]

    submitted = client.post(
        f"/api/tasks/{task['task_id']}/nodes/free/result",
        json={"attempt_no": 1, "result": "已处理"},
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["state"] == "done"
    assert submitted.json()["runs"][0]["result"] == "已处理"

    stale = client.post(
        f"/api/tasks/{task['task_id']}/nodes/free/result",
        json={"attempt_no": 9, "result": "重复"},
        headers=headers,
    )
    assert stale.status_code == 409


def test_human_node_claim_cas_and_final_approval_approve(client) -> None:
    headers = _bootstrap(client)
    workflow_id = _human_graph(client, headers)
    task = _start_task(client, headers, workflow_id)
    assert task["nodes"][0]["state"] == "done"
    assert task["nodes"][1]["state"] == "running"

    claimed = client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/claim", headers=headers
    )
    assert claimed.status_code == 200, claimed.text
    again = client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/claim", headers=headers
    )
    assert again.status_code == 409

    run = claimed.json()["nodes"][1]["runs"][0]
    done = client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/result",
        json={"attempt_no": run["attempt_no"], "result": "完成"},
        headers=headers,
    )
    assert done.status_code == 200, done.text

    approvals = client.get("/api/approvals", headers=headers)
    assert approvals.status_code == 200, approvals.text
    items = approvals.json()["items"]
    assert len(items) == 1
    resolved = client.post(
        f"/api/approvals/{items[0]['approval_id']}/resolve",
        json={"decision": "approved", "comment": "通过"},
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text
    detail = client.get(f"/api/tasks/{task['task_id']}", headers=headers).json()
    assert detail["state"] == "done"


def test_final_approval_reject_without_rework_cancels(client) -> None:
    headers = _bootstrap(client)
    workflow_id = _human_graph(client, headers)
    task = _start_task(client, headers, workflow_id, "驳回任务")
    client.post(f"/api/tasks/{task['task_id']}/nodes/work/claim", headers=headers)
    client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/result",
        json={"attempt_no": 1, "result": "完成"},
        headers=headers,
    )
    item = client.get("/api/approvals", headers=headers).json()["items"][0]
    rejected = client.post(
        f"/api/approvals/{item['approval_id']}/resolve",
        json={"decision": "rejected", "comment": "不合格"},
        headers=headers,
    )
    assert rejected.status_code == 200, rejected.text
    detail = client.get(f"/api/tasks/{task['task_id']}", headers=headers).json()
    assert detail["state"] == "cancelled"
    assert detail["termination_reason"] == "approval_rejected"


def test_cancel_requires_operator_and_marks_reason(client) -> None:
    headers = _bootstrap(client)
    task = client.post("/api/tasks", json={"title": "待取消"}, headers=headers).json()
    cancelled = client.post(
        f"/api/tasks/{task['task_id']}/cancel",
        json={"reason": "manual"},
        headers=headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    assert cancelled.json()["termination_reason"] == "manual"
    again = client.post(
        f"/api/tasks/{task['task_id']}/cancel",
        json={"reason": "manual"},
        headers=headers,
    )
    assert again.status_code == 409

    invalid = client.post("/api/tasks", json={"title": "非法原因"}, headers=headers).json()
    bad = client.post(
        f"/api/tasks/{invalid['task_id']}/cancel",
        json={"reason": "whatever"},
        headers=headers,
    )
    assert bad.status_code == 422


def test_summary_and_list_are_scoped(client) -> None:
    headers = _bootstrap(client)
    client.post("/api/tasks", json={"title": "角标任务"}, headers=headers)
    summary = client.get("/api/tasks/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["mine_open"] >= 1
    listed = client.get("/api/tasks", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] >= 1


def test_failed_result_retries_then_escalates_to_human(client) -> None:
    headers = _bootstrap(client)
    workflow_id = _human_graph(client, headers)
    task = _start_task(client, headers, workflow_id, "会失败的任务")

    first = client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/result",
        json={"attempt_no": 1, "result": '{"status": "failed", "error": "崩了"}'},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    work = first.json()["nodes"][1]
    assert work["state"] == "running"
    assert [run["state"] for run in work["runs"]] == ["failed", "pending"]
    assert work["runs"][1]["attempt_no"] == 2

    # 重试次数用尽：升级并转人工，任务阻塞等待补齐
    second = client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/result",
        json={"attempt_no": 2, "result": '{"status": "failed"}'},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    detail = second.json()
    assert detail["state"] == "blocked"
    assert detail["nodes"][1]["state"] == "blocked"
    assert detail["nodes"][1]["runs"][-1]["state"] == "pending"


def test_final_approval_reject_with_rework_redispatches_node(client) -> None:
    headers = _bootstrap(client)
    position = client.post("/api/positions", json={"name": "执行岗"}, headers=headers)
    position_id = position.json()["position_id"]
    nodes = [_node("start", "start", 0),
             _node("work", "human", 1, position_id=position_id),
             _node("final", "final_approval", 2, position_id=position_id)]
    edges = [_edge("start", "work"), _edge("work", "final"), _edge("final", "work")]
    workflow_id = _published(client, headers, nodes, edges)
    task = _start_task(client, headers, workflow_id, "驳回重做")

    client.post(f"/api/tasks/{task['task_id']}/nodes/work/claim", headers=headers)
    client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/result",
        json={"attempt_no": 1, "result": "初稿"},
        headers=headers,
    )
    approval = client.get("/api/approvals", headers=headers).json()["items"][0]
    rejected = client.post(
        f"/api/approvals/{approval['approval_id']}/resolve",
        json={"decision": "rejected", "comment": "重做"},
        headers=headers,
    )
    assert rejected.status_code == 200, rejected.text
    detail = client.get(f"/api/tasks/{task['task_id']}", headers=headers).json()
    assert detail["state"] == "running"
    assert detail["nodes"][1]["state"] == "running"
    attempts = [run["attempt_no"] for run in detail["nodes"][1]["runs"]]
    assert attempts == [1, 2]


def test_rerun_join_reports_missing_and_writes_audit(client, tmp_path) -> None:
    headers = _bootstrap(client)
    position = client.post("/api/positions", json={"name": "执行岗"}, headers=headers)
    position_id = position.json()["position_id"]
    nodes = [_node("start", "start", 0),
             _node("a", "human", 1, position_id=position_id, max_retries=0,
                   config={"fanout": 2}),
             _node("join", "parallel_join", 2),
             _node("final", "final_approval", 3, position_id=position_id)]
    edges = [_edge("start", "a"), _edge("a", "join"), _edge("join", "final")]
    workflow_id = _published(client, headers, nodes, edges)
    task = _start_task(client, headers, workflow_id, "汇聚缺片")

    # 分片 1 失败且不再重试：节点聚合失败，缺失分片不自动推进
    client.post(f"/api/tasks/{task['task_id']}/nodes/a/result",
                json={"attempt_no": 1, "result": '{"status": "failed"}'},
                headers=headers)
    client.post(f"/api/tasks/{task['task_id']}/nodes/a/result",
                json={"attempt_no": 1, "result": "分片 2 完成"}, headers=headers)
    pending = client.get(f"/api/tasks/{task['task_id']}", headers=headers).json()
    assert pending["nodes"][2]["state"] == "pending"

    forced = client.post(
        f"/api/tasks/{task['task_id']}/nodes/join/rerun-join",
        json={"fanout_group": "g1", "scope": "join"},
        headers=headers,
    )
    assert forced.status_code == 200, forced.text
    detail = forced.json()
    assert detail["nodes"][2]["state"] == "done"
    join_run = detail["nodes"][2]["runs"][-1]
    assert '"forced": true' in join_run["result"]
    assert "a:slot1:failed" in join_run["result"]

    with sqlite3.connect(Settings(data_dir=tmp_path).db_path) as conn:
        rows = conn.execute(
            "SELECT detail FROM ops_audit_log WHERE action = 'task.join_rerun'"
        ).fetchall()
    assert rows and '"scope": "join"' in rows[-1][0]


def test_approval_timeout_escalates_and_expires(client, tmp_path) -> None:
    headers = _bootstrap(client)
    workflow_id = _human_graph(client, headers)
    task = _start_task(client, headers, workflow_id, "审批超时")
    client.post(f"/api/tasks/{task['task_id']}/nodes/work/result",
                json={"attempt_no": 1, "result": "完成"}, headers=headers)
    item = client.get("/api/approvals", headers=headers).json()["items"][0]

    with sqlite3.connect(Settings(data_dir=tmp_path).db_path) as conn:
        conn.execute("UPDATE approval_items SET expires_at = 0 WHERE approval_id = ?",
                     (item["approval_id"],))
        conn.commit()

    client.app.state.container.task_engine.sweep_timeouts()

    approval = client.get("/api/approvals", headers=headers).json()["items"][0]
    assert approval["status"] == "expired"
    with sqlite3.connect(Settings(data_dir=tmp_path).db_path) as conn:
        levels = conn.execute(
            "SELECT reason, level FROM task_escalations WHERE task_id = ?",
            (task["task_id"],),
        ).fetchall()
    assert ("approval_timeout", 1) in levels


def test_upload_artifact_and_attach_to_result(client) -> None:
    headers = _bootstrap(client)
    workflow_id = _human_graph(client, headers)
    task = _start_task(client, headers, workflow_id, "带产物的任务")

    uploaded = client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/artifacts",
        files={"file": ("report.txt", b"hello", "text/plain")},
        data={"description": "阶段报告"},
        headers=headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    artifact = uploaded.json()
    assert artifact["task_id"] == task["task_id"]
    assert artifact["node_id"] == "work"
    assert artifact["file_name"] == "report.txt"
    assert artifact["size_bytes"] == 5
    assert artifact["description"] == "阶段报告"
    assert artifact["created_by"] == task["owner_id"]

    detail = client.get(f"/api/tasks/{task['task_id']}", headers=headers).json()
    assert [item["artifact_id"] for item in detail["artifacts"]] == [artifact["artifact_id"]]

    done = client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/result",
        json={"attempt_no": 1, "result": "完成",
              "artifact_ids": [artifact["artifact_id"]]},
        headers=headers,
    )
    assert done.status_code == 200, done.text

    download = client.get(
        f"/api/artifacts/{artifact['artifact_id']}/download", headers=headers
    )
    assert download.status_code == 200
    assert download.content == b"hello"


def test_upload_artifact_rejects_bad_input(client) -> None:
    headers = _bootstrap(client)
    workflow_id = _human_graph(client, headers)
    task = _start_task(client, headers, workflow_id, "异常上传")

    empty = client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/artifacts",
        files={"file": ("empty.txt", b"", "text/plain")},
        headers=headers,
    )
    assert empty.status_code == 422, empty.text

    foreign = client.post(
        f"/api/tasks/{task['task_id']}/nodes/ghost/artifacts",
        files={"file": ("ghost.txt", b"x", "text/plain")},
        headers=headers,
    )
    assert foreign.status_code == 422, foreign.text

    missing = client.post(
        f"/api/tasks/{task['task_id']}/nodes/work/result",
        json={"attempt_no": 1, "result": "完成", "artifact_ids": ["artifact_missing"]},
        headers=headers,
    )
    assert missing.status_code == 422, missing.text

