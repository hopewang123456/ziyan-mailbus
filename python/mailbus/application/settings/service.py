"""集成与运行配置用例：内置集成清单、插件、env 与重载占位。"""

from __future__ import annotations

from mailbus.application.identity.dto import Actor
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.settings.ports import SettingsStorePort
from mailbus.core.shared.errors import InvalidStateError, NotFoundError
from mailbus.core.shared.values import Capability

_CATALOG = (
    {
        "name": "comfyui",
        "kind": "image",
        "description": "ComfyUI 图像生成",
        "actions": ["probe", "txt2img"],
    },
    {
        "name": "n8n",
        "kind": "automation",
        "description": "n8n 自动化编排",
        "actions": ["probe"],
    },
    {
        "name": "agentmemory",
        "kind": "memory",
        "description": "AgentMemory 共享记忆",
        "actions": ["probe"],
    },
    {
        "name": "gpu",
        "kind": "compute",
        "description": "GPU 资源探测",
        "actions": ["probe"],
    },
)

_ENV_GROUPS = {
    "agentmemory": (
        ("AGENTMEMORY_URL", "共享记忆服务地址", False),
    ),
    "openclaw": (
        ("OPENCLAW_GATEWAY_TOKEN", "OpenClaw Gateway Token", True),
    ),
}
_ALLOWED_ENV = frozenset(
    key for entries in _ENV_GROUPS.values() for key, _, _ in entries
)


class IntegrationService:
    def __init__(self, store: SettingsStorePort) -> None:
        self._store = store

    def list_integrations(self) -> dict:
        data = self._store.read()
        return {
            "integrations": [dict(item) for item in _CATALOG],
            "plugins": _plugins(data),
            "note": "内置集成只做探测合同；插件与 env 持久化在 data/settings.json",
        }

    def mutate_plugins(self, actor: Actor, action: str, spec: str) -> dict:
        self._require(actor)
        name = spec.strip()
        if not name:
            raise InvalidStateError("插件标识不能为空")
        data = self._store.read()
        plugins = _plugins(data)
        if action == "add_plugin":
            if name not in plugins:
                plugins.append(name)
        elif action == "remove_plugin":
            plugins = [item for item in plugins if item != name]
        else:
            raise InvalidStateError("action 只支持 add_plugin / remove_plugin")
        data["plugins"] = plugins
        self._store.write(data)
        return {"plugins": plugins}

    def invoke(self, actor: Actor, name: str, action: str, params: dict) -> dict:
        self._require(actor)
        entry = next((item for item in _CATALOG if item["name"] == name), None)
        if entry is None:
            raise NotFoundError("集成不存在")
        if action not in entry["actions"]:
            raise InvalidStateError(f"集成 {name} 不支持动作 {action}")
        if action == "txt2img":
            return {
                "ok": False,
                "name": name,
                "action": action,
                "error": "not_configured",
                "prompt": str(params.get("prompt", "")),
            }
        return {
            "ok": False,
            "name": name,
            "action": action,
            "error": "not_configured",
            "detail": "尚未配置外部地址，仅返回探测合同",
        }

    def env_groups(self) -> dict:
        values = self._store.read().get("env", {})
        groups: dict[str, list[dict]] = {}
        for group, entries in _ENV_GROUPS.items():
            groups[group] = [
                {
                    "key": key,
                    "label": label,
                    "value": "" if secret else str(values.get(key, "")),
                    "configured": bool(values.get(key)),
                }
                for key, label, secret in entries
            ]
        return {"groups": groups}

    def update_env(self, actor: Actor, values: dict) -> dict:
        self._require(actor)
        unknown = set(values) - _ALLOWED_ENV
        if unknown:
            raise InvalidStateError(
                f"不支持的配置项：{', '.join(sorted(unknown))}"
            )
        data = self._store.read()
        env = dict(data.get("env", {}))
        for key, value in values.items():
            text = "" if value is None else str(value).strip()
            if text:
                env[key] = text
            else:
                env.pop(key, None)
        data["env"] = env
        self._store.write(data)
        return self.env_groups()

    def reload(self, actor: Actor) -> dict:
        self._require(actor)
        return {"reloaded": False, "plugins": _plugins(self._store.read())}

    @staticmethod
    def _require(actor: Actor) -> None:
        ensure_allowed(
            actor.to_subject(), Capability.SYSTEM_CONFIG, Resource(kind="integration")
        )


def _plugins(data: dict) -> list[str]:
    return [
        str(item) for item in data.get("plugins", []) if isinstance(item, str)
    ]
