"""M12：非系统配置账号读取技能/Agent 元数据时隐藏敏感字段。"""

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


def _create_plain_user(client: TestClient, admin: dict[str, str]) -> str:
    invite = client.post(
        "/api/identity/invites",
        json={"account_type": "human", "capabilities": []},
        headers=admin,
    ).json()
    applied = client.post(
        "/api/identity/staff",
        json={
            "display_name": "普通员工",
            "account_type": "human",
            "invite_code": invite["invite_code"],
        },
    ).json()
    return applied["token"]


def test_skills_and_agents_metadata_redacted_for_non_privileged(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))

        skill = client.post(
            "/api/skills",
            json={
                "name": "research",
                "source_type": "http",
                "source_uri": "http://127.0.0.1:9/vault/research",
                "entry": "SKILL.md",
            },
            headers=admin,
        )
        assert skill.status_code == 201, skill.text

        agent = client.post(
            "/api/agents",
            json={"name": "研究员", "endpoint": "http://127.0.0.1:9001"},
            headers=admin,
        )
        assert agent.status_code == 201, agent.text

        # 管理员可见全部敏感字段
        admin_skill = client.get("/api/skills", headers=admin).json()[0]
        assert admin_skill["source_uri"] == "http://127.0.0.1:9/vault/research"
        assert admin_skill["entry"] == "SKILL.md"
        admin_agent = client.get("/api/agents", headers=admin).json()[0]
        assert admin_agent["endpoint"] == "http://127.0.0.1:9001"

        user = _headers(_create_plain_user(client, admin))

        # 非特权账号：来源路径 / 入口 / 端点均被隐藏
        user_skill = client.get("/api/skills", headers=user).json()[0]
        assert user_skill["source_uri"] is None
        assert user_skill["entry"] is None

        # M12：非特权账号不能查询他人 Agent 的有效技能（归属校验）
        eff = client.get(
            "/api/skills/effective",
            params={"target_type": "agent", "target_id": agent.json()["agent_id"]},
            headers=user,
        )
        assert eff.status_code == 403, eff.text

        user_agent = client.get("/api/agents", headers=user).json()[0]
        assert user_agent["endpoint"] is None
        # 非敏感字段仍可见
        assert user_agent["name"] == "研究员"
        assert user_skill["name"] == "research"
