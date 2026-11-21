"""M13：首启超管仅允许本机来源，可用环境变量放开。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def test_bootstrap_rejects_public_client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app, client=("203.0.113.10", 50000)) as client:
        response = client.post(
            "/api/identity/bootstrap/super-admin", json={"display_name": "公网"}
        )
        assert response.status_code == 403, response.text


def test_bootstrap_allows_private_network_client(tmp_path):
    """容器/局域网来源（私网地址）仍可完成首次初始化。"""
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app, client=("172.17.0.1", 50000)) as client:
        response = client.post(
            "/api/identity/bootstrap/super-admin", json={"display_name": "内网"}
        )
        assert response.status_code == 201, response.text


def test_bootstrap_allows_remote_when_enabled(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, bootstrap_allow_remote=True))
    with TestClient(app, client=("203.0.113.10", 50000)) as client:
        response = client.post(
            "/api/identity/bootstrap/super-admin", json={"display_name": "远程"}
        )
        assert response.status_code == 201, response.text
