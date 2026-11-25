"""B8 测试共用：新契约下的身份、Agent 与工位操作。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def bootstrap(client: TestClient) -> str:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def create_human(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    **invite_fields,
) -> tuple[str, str | None]:
    """经邀请码创建一个已激活的真人员工，返回 (employee_id, token)。"""
    invite = client.post(
        "/api/employees/invite",
        json={"display_name": name, **invite_fields},
        headers=admin_headers,
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"], "display_name": name},
    )
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()
    return body["employee"]["employee_id"], body["token"]


def create_agent(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    **invite_fields,
) -> dict:
    """签发 Agent 邀请并完成自助注册，返回注册响应（含 agent_id/token）。"""
    invite = client.post(
        "/api/agent-invites",
        json={"employee_name": name, **invite_fields},
        headers=admin_headers,
    )
    assert invite.status_code == 201, invite.text
    registered = client.post(
        "/api/agents/register",
        json={"invite_code": invite.json()["invite_code"], "name": name},
    )
    assert registered.status_code == 201, registered.text
    return registered.json()


def seat_ids(client: TestClient, auth: dict[str, str]) -> list[str]:
    site = client.get("/api/layout", headers=auth).json()
    return [
        seat["seat_id"]
        for floor in site["floors"]
        for room in floor["rooms"]
        for seat in room["seats"]
    ]


def assign_seat(
    client: TestClient,
    auth: dict[str, str],
    seat_id: str,
    *,
    employee_id: str | None = None,
    team_id: str | None = None,
    position_id: str | None = None,
):
    return client.put(
        f"/api/seats/{seat_id}/assign",
        json={
            "employee_id": employee_id,
            "team_id": team_id,
            "position_id": position_id,
        },
        headers=auth,
    )
