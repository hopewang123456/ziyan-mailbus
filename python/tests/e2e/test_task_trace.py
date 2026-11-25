"""任务追迹契约：由任务与 run 投影生成有序时间线。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings
from tests.e2e._support import bootstrap, create_human, headers


def _event(trace: dict, kind: str) -> dict:
    return next(event for event in trace["events"] if event["kind"] == kind)


def test_task_trace_uses_persistent_projection_and_task_visibility(tmp_path) -> None:
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        admin = headers(bootstrap(client))
        created = client.post("/api/tasks", json={"title": "可追迹任务"}, headers=admin)
        assert created.status_code == 201, created.text
        task = created.json()
        task_id = task["task_id"]
        run = task["runs"][0]

        initial = client.get(f"/api/tasks/{task_id}/trace", headers=admin)
        assert initial.status_code == 200, initial.text
        assert initial.json()["task_id"] == task_id
        assert [event["kind"] for event in initial.json()["events"]] == [
            "task.created", "run.dispatched"
        ]
        created_event = _event(initial.json(), "task.created")
        assert created_event["at"] == task["created_at"]
        assert created_event["detail"] == {"title": "可追迹任务", "state": "running"}
        dispatched = _event(initial.json(), "run.dispatched")
        assert dispatched["run_id"] == run["run_id"]
        assert dispatched["node_id"] == "free"
        assert dispatched["attempt_no"] == 1
        assert dispatched["detail"]["state"] == "running"

        submitted = client.post(
            f"/api/tasks/{task_id}/nodes/free/result",
            json={"attempt_no": 1, "result": "完成"},
            headers=admin,
        )
        assert submitted.status_code == 200, submitted.text
        traced = client.get(f"/api/tasks/{task_id}/trace", headers=admin)
        assert traced.status_code == 200, traced.text
        events = traced.json()["events"]
        assert [event["kind"] for event in events] == [
            "task.created", "run.dispatched", "run.started", "run.completed"
        ]
        assert [event["at"] for event in events] == sorted(event["at"] for event in events)
        for kind in ("run.dispatched", "run.started", "run.completed"):
            event = _event(traced.json(), kind)
            assert event["run_id"] == run["run_id"]
            assert event["node_id"] == run["node_id"]
            assert event["attempt_no"] == run["attempt_no"]
            assert event["detail"]["state"] == "done"

        assert client.get("/api/tasks/task_missing/trace", headers=admin).status_code == 404
        _, staff_token = create_human(client, admin, "无任务范围员工")
        forbidden = client.get(f"/api/tasks/{task_id}/trace", headers=headers(staff_token))
        assert forbidden.status_code == 403, forbidden.text
