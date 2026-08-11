"""Compose 服务名解析 — transport docker 字段 → 实际 docker-compose service。"""

from __future__ import annotations

# 逻辑 build 名 → compose service（多 agent 共享容器时用 agent_id 细分）
LOGICAL_TO_COMPOSE: dict[str, str] = {
    "codex-agent": "lingxiao",  # 默认；lingjian 用 agent_id 覆盖
    "opencode-agent": "dali",
    "openclaw-agent": "openclaw",
    "hermes-agent": "hermes",
    "claude-agent": "",
}

# agent_id → compose service（Codex 等多实例）
AGENT_COMPOSE_SERVICE: dict[str, str] = {
    "lingxiao": "lingxiao",
    "lingjian": "lingjian",
    "dali": "dali",
    "xiaoqi": "openclaw",
    "yige": "openclaw",
    "lingzhao": "hermes",
    "lingjin": "hermes",
    "lingxi": "hermes",
    "lingtuo": "hermes",
    "lingxun": "hermes",
    "lingzhang": "hermes",
}


def resolve_compose_service(agent_id: str, docker_cfg: dict | None) -> str:
    """返回 docker-compose.yml 中的 service 名。"""
    docker_cfg = docker_cfg or {}
    if docker_cfg.get("compose_service"):
        return str(docker_cfg["compose_service"]).strip()
    logical = (docker_cfg.get("service") or "").strip()
    if agent_id in AGENT_COMPOSE_SERVICE:
        return AGENT_COMPOSE_SERVICE[agent_id]
    if logical in LOGICAL_TO_COMPOSE:
        mapped = LOGICAL_TO_COMPOSE[logical]
        if mapped:
            return mapped
    if logical and logical not in LOGICAL_TO_COMPOSE:
        # already a compose name (hermes, lingxiao, openclaw, dali)
        return logical
    return agent_id


def agent_compose_services() -> set[str]:
    return {"mailbus", "iii-engine", "agentmemory", "hermes", "openclaw", "lingxiao", "lingjian", "dali"}
