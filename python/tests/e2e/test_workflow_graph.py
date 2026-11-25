"""B3 工作流域端到端：Graph 读写、乐观锁、发布校验、派生与审计。"""

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


def _bootstrap(client: TestClient) -> str:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _node(
    node_id: str,
    node_type: str,
    seq: int,
    position_id: str | None = None,
    prompt: str | None = None,
    config: dict | None = None,
) -> dict:
    return {
        "node_id": node_id,
        "name": node_id,
        "node_type": node_type,
        "position_id": position_id,
        "seq": seq,
        "prompt_template": prompt,
        "needs_artifacts_from": [],
        "max_retries": 3,
        "max_loops": 3,
        "timeout_seconds": None,
        "config": config or {},
        "pos_x": seq * 120,
        "pos_y": 0,
    }


def _edge(source: str, target: str, condition: str | None = None) -> dict:
    return {"from_node_id": source, "to_node_id": target, "condition": condition}


def _graph(final_edges: list[dict] | None = None) -> dict:
    nodes = [
        _node("start", "start", 0),
        _node("collect", "agent", 1, "pos_1", "处理 {{task.title}}"),
        _node("review", "human", 2, "pos_2", "请审核"),
        _node("final", "final_approval", 3, "pos_3"),
    ]
    edges = [
        _edge("start", "collect"),
        _edge("collect", "review"),
        _edge("review", "final"),
        *(final_edges or []),
    ]
    return {"nodes": nodes, "edges": edges}


def _create(client: TestClient, headers: dict[str, str], graph: dict | None) -> dict:
    response = client.post(
        "/api/workflows",
        json={"name": "内容生产", "graph": graph},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_graph_create_read_and_revision_conflict(client, tmp_path) -> None:
    headers = _headers(_bootstrap(client))
    flow = _create(client, headers, _graph())
    assert flow["latest_version"] == 1

    read = client.get(
        f"/api/workflows/{flow['workflow_id']}/versions/1/graph", headers=headers
    )
    assert read.status_code == 200, read.text
    assert read.json()["revision"] == 1
    types = [node["node_type"] for node in read.json()["graph"]["nodes"]]
    assert types == ["start", "agent", "human", "final_approval"]

    payload = {"graph": _graph(), "revision": 1}
    saved = client.put(
        f"/api/workflows/{flow['workflow_id']}/versions/1/graph",
        json=payload,
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 2

    stale = client.put(
        f"/api/workflows/{flow['workflow_id']}/versions/1/graph",
        json=payload,
        headers=headers,
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["revision"] == 2

    forced = client.put(
        f"/api/workflows/{flow['workflow_id']}/versions/1/graph?force=true",
        json=payload,
        headers=headers,
    )
    assert forced.status_code == 200, forced.text
    assert forced.json()["revision"] == 3

    with sqlite3.connect(Settings(data_dir=tmp_path).db_path) as conn:
        rows = conn.execute(
            "SELECT detail FROM ops_audit_log WHERE action = 'workflow.graph_save'"
            " ORDER BY audit_id"
        ).fetchall()
    details = [json.loads(row[0]) for row in rows]
    assert [item["force"] for item in details] == [False, True]
    assert details[-1]["revision"] == 3
    assert details[-1]["base_revision"] == 2


def test_structural_errors_block_put(client) -> None:
    headers = _headers(_bootstrap(client))
    flow = _create(client, headers, _graph())
    duplicate = _graph()
    duplicate["nodes"].append(_node("review", "human", 9, "pos_2"))
    broken = client.put(
        f"/api/workflows/{flow['workflow_id']}/versions/1/graph",
        json={"graph": duplicate, "revision": 1},
        headers=headers,
    )
    assert broken.status_code == 400, broken.text
    assert broken.json()["errors"][0]["code"] == "E_DUPLICATE_NODE_ID"

    dangling = _graph()
    dangling["edges"].append(_edge("review", "ghost"))
    broken = client.put(
        f"/api/workflows/{flow['workflow_id']}/versions/1/graph",
        json={"graph": dangling, "revision": 1},
        headers=headers,
    )
    assert broken.status_code == 400, broken.text
    assert broken.json()["errors"][0]["code"] == "E_DANGLING_EDGE"


def test_validate_reports_codes_without_persisting(client) -> None:
    headers = _headers(_bootstrap(client))
    flow = _create(client, headers, _graph())
    no_final = _graph()
    no_final["nodes"] = [node for node in no_final["nodes"] if node["node_id"] != "final"]
    no_final["edges"] = [
        edge for edge in no_final["edges"] if edge["to_node_id"] != "final"
    ]
    checked = client.post(
        f"/api/workflows/{flow['workflow_id']}/versions/1/validate",
        json={"graph": no_final, "revision": 1},
        headers=headers,
    )
    assert checked.status_code == 200, checked.text
    body = checked.json()
    assert body["ok"] is False
    assert "E_NO_FINAL" in {item["code"] for item in body["errors"]}
    assert body["stats"]["node_count"] == 3

    stored = client.get(
        f"/api/workflows/{flow['workflow_id']}/versions/1/graph", headers=headers
    )
    assert stored.json()["revision"] == 1


def test_join_required_and_final_rework(client) -> None:
    headers = _headers(_bootstrap(client))
    flow = _create(client, headers, _graph())
    base = _graph()
    base["nodes"].append(_node("extra", "agent", 4, "pos_1", "补充 {{task.title}}"))
    base["edges"] = [
        _edge("start", "collect"),
        _edge("collect", "review"),
        _edge("collect", "extra"),
        _edge("extra", "review"),
        _edge("review", "final"),
    ]
    checked = client.post(
        f"/api/workflows/{flow['workflow_id']}/versions/1/validate",
        json={"graph": base, "revision": 1},
        headers=headers,
    ).json()
    codes = {item["code"] for item in checked["errors"]}
    assert "E_MULTI_IN_REQUIRES_JOIN" in codes
    assert "E_MIXED_OUT_EDGES" not in codes

    two_rework = _graph([_edge("final", "review"), _edge("final", "collect")])
    checked = client.post(
        f"/api/workflows/{flow['workflow_id']}/versions/1/validate",
        json={"graph": two_rework, "revision": 1},
        headers=headers,
    ).json()
    assert "E_FINAL_REWORK_EDGES" in {item["code"] for item in checked["errors"]}

    valid_with_join = _graph()
    valid_with_join["nodes"] = _graph()["nodes"][:3] + [
        _node("merge", "parallel_join", 3),
        _node("final", "final_approval", 4, "pos_3"),
    ]
    valid_with_join["edges"] = [
        _edge("start", "collect"),
        _edge("collect", "review"),
        _edge("review", "merge"),
        _edge("merge", "final"),
    ]
    ok = client.post(
        f"/api/workflows/{flow['workflow_id']}/versions/1/validate",
        json={"graph": valid_with_join, "revision": 1},
        headers=headers,
    ).json()
    assert ok["ok"] is True, ok


def test_publish_blocks_invalid_and_freezes_published(client) -> None:
    headers = _headers(_bootstrap(client))
    flow = _create(client, headers, _graph())
    bad = _graph()
    bad["nodes"] = [node for node in bad["nodes"] if node["node_id"] != "final"]
    bad["edges"] = [edge for edge in bad["edges"] if edge["to_node_id"] != "final"]
    saved = client.put(
        f"/api/workflows/{flow['workflow_id']}/versions/1/graph",
        json={"graph": bad, "revision": 1},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    blocked = client.post(
        f"/api/workflows/{flow['workflow_id']}/versions/1/publish", headers=headers
    )
    assert blocked.status_code == 422, blocked.text
    assert "E_NO_FINAL" in {
        item["code"] for item in blocked.json()["errors"]
    }

    fixed = client.put(
        f"/api/workflows/{flow['workflow_id']}/versions/1/graph",
        json={"graph": _graph(), "revision": 2},
        headers=headers,
    )
    assert fixed.status_code == 200, fixed.text
    published = client.post(
        f"/api/workflows/{flow['workflow_id']}/versions/1/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    assert published.json()["state"] == "published"

    frozen = client.put(
        f"/api/workflows/{flow['workflow_id']}/versions/1/graph",
        json={"graph": _graph(), "revision": 3},
        headers=headers,
    )
    assert frozen.status_code == 409, frozen.text


def test_clone_lists_and_soft_delete(client) -> None:
    headers = _headers(_bootstrap(client))
    flow = _create(client, headers, _graph())
    clone = client.post(
        f"/api/workflows/{flow['workflow_id']}/versions/1/clone", headers=headers
    )
    assert clone.status_code == 201, clone.text
    assert clone.json()["version"] == 2
    assert clone.json()["state"] == "draft"
    assert clone.json()["revision"] == 1

    versions = client.get(
        f"/api/workflows/{flow['workflow_id']}/versions", headers=headers
    ).json()
    assert [item["version"] for item in versions["items"]] == [1, 2]
    assert versions["total"] == 2

    copied = client.get(
        f"/api/workflows/{flow['workflow_id']}/versions/2/graph", headers=headers
    ).json()
    assert len(copied["graph"]["nodes"]) == 4

    deleted = client.delete(f"/api/workflows/{flow['workflow_id']}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    listing = client.get("/api/workflows", headers=headers).json()
    assert flow["workflow_id"] not in {item["workflow_id"] for item in listing["items"]}
    assert listing["total"] == 0
    assert (
        client.get(f"/api/workflows/{flow['workflow_id']}", headers=headers).status_code
        == 404
    )
