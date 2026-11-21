"""M13：匿名入伙申请按 IP 限流，阻断账号注册洪水。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def test_public_apply_is_rate_limited(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        client.post(
            "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
        )
        for index in range(5):
            resp = client.post(
                "/api/identity/staff",
                json={"display_name": f"申请人{index}", "account_type": "human"},
            )
            assert resp.status_code == 201, resp.text

        blocked = client.post(
            "/api/identity/staff",
            json={"display_name": "溢出", "account_type": "human"},
        )
        assert blocked.status_code == 429, blocked.text
        assert blocked.json()["error_code"] == "rate_limited"
