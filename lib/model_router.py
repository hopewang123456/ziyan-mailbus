"""按消息类型/优先级选择 DeepSeek 模型档位（flash vs pro）。

默认 **全部 flash**（deepseek-chat），省 token。
仅当消息显式 `action.model_tier: "pro"` 且 agent 的 models 含 deepseek-pro，
或环境变量 `MAILBUS_ALLOW_PRO=1` 时，才走 pro（deepseek-v4-pro / reasoner）。
"""

from __future__ import annotations

import os
from typing import Any, Optional

TIER_FLASH = "deepseek-flash"
TIER_PRO = "deepseek-pro"
TIER_OLLAMA = "ollama-local"

NO_LLM_NOTICE_MARKERS = (
    "超时提醒",
    "催办提醒",
    "inbox_overflow",
    "规则更新通知",
    "团队规范已更新",
    "team-secrets-policy",
    "execution-order.md",
    "agent 离线",
    "offline",
    "key_missing",
    "API Key 缺失",
    "执行定时巡检",
    "生成日报",
    "Dashboard",
    "已自动消化",
    "零 token",
)

NO_LLM_ID_PREFIXES = (
    "remind-",
    "tracker-remind-",
    "exec-remind-",
    "rule-change-",
    "alert-task-",
    "heartbeat-",
    "patrol-",
    "confirm-",
    "notice-",
    "reply-patrol-",
    "sys-welcome-",
    "offline-",
)


def _msg_field(msg: Any, key: str, default: str = "") -> str:
    if isinstance(msg, dict):
        return msg.get(key, default) or default
    return getattr(msg, key, default) or default


def _action_dict(msg: Any) -> dict:
    action = _msg_field(msg, "action", {})
    return action if isinstance(action, dict) else {}


def _pro_allowed(agent_cfg: dict) -> bool:
    """Pro 必须显式开启 MAILBUS_ALLOW_PRO=1，且 agent models 含 deepseek-pro。"""
    if os.environ.get("MAILBUS_ALLOW_PRO", "").lower() not in ("1", "true", "yes"):
        return False
    models = (agent_cfg or {}).get("models") or []
    return TIER_PRO in models


def is_no_llm_notice(msg: Any) -> bool:
    """仅系统 notice / 催办 / 规则广播 — mailbus 自行消化，不 spawn agent。"""
    action = _action_dict(msg)
    if action.get("no_llm") is True:
        return True
    mid = _msg_field(msg, "id", "")
    if any(mid.startswith(p) for p in NO_LLM_ID_PREFIXES):
        return True
    mtype = _msg_field(msg, "type", "notice")
    from_ = _msg_field(msg, "from", "")
    if mtype == "system" and from_ in ("mailbus", "system"):
        return True
    if mtype != "notice":
        return False
    content = _msg_field(msg, "content", "")
    if any(x in content for x in NO_LLM_NOTICE_MARKERS):
        return True
    if from_ in ("mailbus", "system"):
        return True
    return False


def pick_model_alias(
    msg: Any,
    agent_name: str,
    agent_cfg: dict,
    *,
    primary_task_id: str = "",
    config: dict | None = None,
    data_dir: str = "",
    routing_out: dict | None = None,
) -> str:
    """为单条推送消息选择 config.models 别名。默认 flash。"""
    if is_no_llm_notice(msg):
        return TIER_FLASH

    action = _action_dict(msg)
    if action.get("model_tier") == "flash":
        return TIER_FLASH
    if action.get("model_tier") in ("ollama", "local"):
        from .ollama_routing import agent_supports_ollama, is_ollama_ready

        atypes = (config or {}).get("agent_types") or {}
        if (
            config
            and is_ollama_ready(config, data_dir=data_dir)
            and agent_supports_ollama(agent_cfg, atypes)
        ):
            return TIER_OLLAMA
        return TIER_FLASH
    if action.get("model_tier") == "pro" and _pro_allowed(agent_cfg):
        return TIER_PRO

    if config is not None:
        from .complexity_router import log_routing_decision, suggest_model_alias

        suggestion = suggest_model_alias(
            msg,
            agent_cfg,
            config=config,
            data_dir=data_dir,
            primary_task_id=primary_task_id,
            agent_types=(config or {}).get("agent_types") or {},
        )
        if suggestion:
            if routing_out is not None:
                routing_out.update(suggestion)
            log_routing_decision(
                data_dir,
                suggestion,
                agent_name=agent_name,
                config=config,
            )
            return suggestion["model_alias"]

    # agent / 全局默认（均为 flash，除非显式配 pro 且 ALLOW）
    default = (agent_cfg or {}).get("default_model_tier")
    if not default:
        default = os.environ.get("MAILBUS_DEFAULT_MODEL_TIER", TIER_FLASH)
    models = (agent_cfg or {}).get("models") or []
    if default == TIER_PRO and _pro_allowed(agent_cfg) and default in models:
        return TIER_PRO
    if default in models:
        return default
    if TIER_FLASH in models:
        return TIER_FLASH
    return models[0] if models else TIER_FLASH
