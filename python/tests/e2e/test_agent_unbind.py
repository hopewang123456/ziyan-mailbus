"""Agent 解绑契约：幂等清空员工绑定，并允许随后注销。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings
from tests.e2e._support import bootstrap, create_agent, headers


def test_agent_unbind_is_idempotent_and_allows_delete(tmp_path) -> None:
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        admin = headers(bootstrap(client))
        position = client.post("/api/positions", json={"name": "执行岗"}, headers=admin)
        assert position.status_code == 201, position.text
        agent = create_agent(
            client, admin, "待解绑 Agent", position_id=position.json()["position_id"]
        )
        agent_id = agent["agent_id"]

        blocked = client.delete(f"/api/agents/{agent_id}", headers=admin)
        assert blocked.status_code == 409, blocked.text

        unbound = client.post(f"/api/agents/{agent_id}/unbind", headers=admin)
        assert unbound.status_code == 200, unbound.text
        assert unbound.json()["agent_id"] == agent_id

        employee = client.get(f"/api/employees/{agent['employee_id']}", headers=admin)
        assert employee.status_code == 200, employee.text
        assert employee.json()["agent_id"] is None

        repeated = client.post(f"/api/agents/{agent_id}/unbind", headers=admin)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["agent_id"] == agent_id

        deleted = client.delete(f"/api/agents/{agent_id}", headers=admin)
        assert deleted.status_code == 204, deleted.text
        assert client.post(f"/api/agents/{agent_id}/unbind", headers=admin).status_code == 404
        assert client.post("/api/agents/agent_missing/unbind", headers=admin).status_code == 404
