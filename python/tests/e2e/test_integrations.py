"""集成契约端到端：清单、插件、env 与重载。"""

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


def test_integrations_plugins_env_and_reload(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))

        listed = client.get("/api/settings/integrations", headers=headers)
        assert listed.status_code == 200, listed.text
        body = listed.json()
        names = {item["name"] for item in body["integrations"]}
        assert {"comfyui", "n8n", "agentmemory"} <= names
        assert body["plugins"] == []

        added = client.post(
            "/api/settings/integrations",
            json={"action": "add_plugin", "spec": "custom_plugin"},
            headers=headers,
        )
        assert added.status_code == 200, added.text
        assert added.json()["plugins"] == ["custom_plugin"]
        assert client.get(
            "/api/settings/integrations", headers=headers
        ).json()["plugins"] == ["custom_plugin"]

        removed = client.post(
            "/api/settings/integrations",
            json={"action": "remove_plugin", "spec": "custom_plugin"},
            headers=headers,
        )
        assert removed.json()["plugins"] == []

        env = client.get("/api/settings/env", headers=headers)
        assert env.status_code == 200, env.text
        keys = {
            item["key"]
            for entries in env.json()["groups"].values()
            for item in entries
        }
        assert {"AGENTMEMORY_URL", "OPENCLAW_GATEWAY_TOKEN"} <= keys

        saved = client.post(
            "/api/settings/env",
            json={"vars": {"AGENTMEMORY_URL": "http://127.0.0.1:8000"}},
            headers=headers,
        )
        assert saved.status_code == 200, saved.text
        entry = next(
            item
            for entries in saved.json()["groups"].values()
            for item in entries
            if item["key"] == "AGENTMEMORY_URL"
        )
        assert entry["value"] == "http://127.0.0.1:8000"
        assert entry["configured"] is True

        secret = client.post(
            "/api/settings/env",
            json={"vars": {"OPENCLAW_GATEWAY_TOKEN": "secret"}},
            headers=headers,
        )
        token_entry = next(
            item
            for entries in secret.json()["groups"].values()
            for item in entries
            if item["key"] == "OPENCLAW_GATEWAY_TOKEN"
        )
        assert token_entry["value"] == ""
        assert token_entry["configured"] is True

        rejected = client.post(
            "/api/settings/env",
            json={"vars": {"UNKNOWN": "x"}},
            headers=headers,
        )
        assert rejected.status_code == 409

        reloaded = client.post("/api/dev/reload", headers=headers)
        assert reloaded.status_code == 200, reloaded.text
        assert reloaded.json()["reloaded"] is True

        invoked = client.post(
            "/api/settings/integrations/comfyui/invoke",
            json={"action": "probe", "params": {}},
            headers=headers,
        )
        assert invoked.status_code == 200, invoked.text
        assert invoked.json()["ok"] is False
