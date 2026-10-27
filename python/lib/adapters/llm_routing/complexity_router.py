"""轻量复杂度路由 — 借鉴 OpenSquilla 思想；可与本机 Ollama 融合（零 API Token）。

混合特征打分 → L0–L3 → flash / ollama-local / pro。
Ollama 可用时优先吃本机 GPU；不可用则回落云端 flash。
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Optional

from lib.adapters.integrations.model_router import TIER_FLASH, TIER_OLLAMA, TIER_PRO, _pro_allowed

COMPLEXITY_TIERS = ("L0", "L1", "L2", "L3")
ENGINE_VERSION = "mailbus-smart-routing"

# Ollama 不可用时回落
DEFAULT_TIER_MAP_CLOUD = {
    "L0": TIER_FLASH,
    "L1": TIER_FLASH,
    "L2": TIER_FLASH,
    "L3": TIER_PRO,
}

# Ollama 可用：L0–L2 走本机，L3 走云端 Pro（须 ALLOW）或继续 Ollama
DEFAULT_TIER_MAP_OLLAMA = {
    "L0": TIER_OLLAMA,
    "L1": TIER_OLLAMA,
    "L2": TIER_OLLAMA,
    "L3": TIER_PRO,
}

DEFAULT_TIER_MAP = dict(DEFAULT_TIER_MAP_CLOUD)

DEFAULT_SMART_ROUTING_CONFIG = {
    "enabled": True,
    "use_ollama": True,
    "log_decisions": False,
    "tier_map": {},
}
_SECURITY_KEYWORDS = (
    "security", "audit", "vulnerability", "crypto", "injection", "secret",
    "安全", "漏洞", "审计", "加密", "注入",
)
_COMPLEX_KEYWORDS = (
    "architecture", "refactor", "ensemble", "design", "pipeline", "migrate",
    "架构", "重构", "设计", "迁移", "预研",
)
_SIMPLE_KEYWORDS = (
    "ack", "已读", "mark-read", "ping", "heartbeat", "巡检", "日报",
    "remind", "催办", "通知", "notice",
)
_CODE_BLOCK_RE = re.compile(r"```")


def _msg_field(msg: Any, key: str, default: str = "") -> str:
    if isinstance(msg, dict):
        return msg.get(key, default) or default
    return getattr(msg, key, default) or default


def _action_dict(msg: Any) -> dict:
    action = _msg_field(msg, "action", {})
    return action if isinstance(action, dict) else {}


def _routing_config_root(config: Optional[dict]) -> dict:
    """读取 smart_routing 根配置。"""
    if not config:
        return {}
    sr = config.get("smart_routing")
    return sr if isinstance(sr, dict) else {}


def load_smart_routing_config(config: Optional[dict], agent_cfg: Optional[dict] = None) -> dict:
    out = dict(DEFAULT_SMART_ROUTING_CONFIG)
    root = _routing_config_root(config)
    if root:
        out.update({k: v for k, v in root.items() if k != "tier_map"})
        tier_map = root.get("tier_map")
        if isinstance(tier_map, dict):
            merged = dict(DEFAULT_TIER_MAP_CLOUD)
            for k, v in tier_map.items():
                nk = str(k).upper().replace("C", "L") if str(k).startswith("C") else str(k).upper()
                merged[nk] = v
            out["tier_map"] = merged
    agent_sr = (agent_cfg or {}).get("smart_routing") or {}
    if isinstance(agent_sr, dict):
        if "enabled" in agent_sr:
            out["enabled"] = bool(agent_sr["enabled"])
        if "log_decisions" in agent_sr:
            out["log_decisions"] = bool(agent_sr["log_decisions"])
        if isinstance(agent_sr.get("tier_map"), dict):
            merged = dict(out.get("tier_map", DEFAULT_TIER_MAP_CLOUD))
            for k, v in agent_sr["tier_map"].items():
                nk = str(k).upper().replace("C", "L") if str(k).startswith("C") else str(k).upper()
                merged[nk] = v
            out["tier_map"] = merged
    return out


def smart_routing_enabled(config: Optional[dict], agent_cfg: Optional[dict] = None) -> bool:
    return bool(load_smart_routing_config(config, agent_cfg).get("enabled"))


def _content_hash(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    return f"sha256:{digest[:16]}"


def build_features(
    msg: Any,
    *,
    data_dir: str = "",
    primary_task_id: str = "",
) -> dict[str, Any]:
    content = _msg_field(msg, "content", "")
    action = _action_dict(msg)
    text = content or ""
    lower = text.lower()
    features: dict[str, Any] = {
        "text": text,
        "content_length": len(text),
        "has_code_block": bool(_CODE_BLOCK_RE.search(text)),
        "has_security_keyword": any(k in lower for k in _SECURITY_KEYWORDS),
        "has_complex_keyword": any(k in lower for k in _COMPLEX_KEYWORDS),
        "has_simple_keyword": any(k in lower for k in _SIMPLE_KEYWORDS),
        "intent": action.get("intent") or _msg_field(msg, "intent", ""),
        "priority": (_msg_field(msg, "priority", "") or "").lower(),
        "msg_id": _msg_field(msg, "id", ""),
        "msg_type": _msg_field(msg, "type", "notice"),
        "task_type": "",
        "task_tier": "",
        "pipeline_step_index": 0,
    }
    tid = primary_task_id or action.get("task_id") or ""
    if data_dir and tid:
        try:
            from lib.infra.utils import json_read

            task = json_read(os.path.join(data_dir, "tasks", f"{tid}.json"), {})
            if task:
                features["task_type"] = (task.get("task_type") or "").lower()
                features["task_tier"] = (task.get("tier") or "").upper()
                chain = task.get("chain") or []
                cur = task.get("current_step") or task.get("current_step_id")
                for i, step in enumerate(chain):
                    sid = step.get("step_id") or step.get("id")
                    if sid and sid == cur:
                        features["pipeline_step_index"] = i
                        break
        except Exception:
            pass
    return features


def score_complexity(features: dict[str, Any]) -> int:
    """混合特征打分（纯 CPU，借鉴 SquillaRouter 特征维度，无 ML）。"""
    score = 0
    length = int(features.get("content_length") or 0)

    if features.get("has_simple_keyword") and length < 200 and not features.get("has_code_block"):
        return 0

    if length < 120:
        score += 0
    elif length < 350:
        score += 1
    elif length < 700:
        score += 2
    else:
        score += 3

    if features.get("has_code_block"):
        score += 1
    if features.get("has_security_keyword"):
        score += 2
    if features.get("has_complex_keyword"):
        score += 1
    if features.get("task_tier") == "L":
        score += 1
    if int(features.get("pipeline_step_index") or 0) >= 3:
        score += 1
    if features.get("task_type") in ("security_review", "full_delivery"):
        score += 1
    if features.get("priority") == "urgent" and length > 300:
        score += 1
    if features.get("msg_type") == "notice" and length < 150:
        score = min(score, 1)

    return score


def classify_complexity(features: dict[str, Any]) -> str:
    """L0–L3 复杂度档（mailbus 原生命名，不绑定 OpenSquilla）。"""
    score = score_complexity(features)
    if score <= 1:
        return "L0"
    if score <= 3:
        return "L1"
    if score <= 5:
        return "L2"
    return "L3"


def resolve_effective_tier_map(
    routing_cfg: dict,
    *,
    config: Optional[dict] = None,
    data_dir: str = "",
    agent_cfg: Optional[dict] = None,
    agent_types: Optional[dict] = None,
) -> dict[str, str]:
    """按 Ollama 可达性选择 tier_map；显式 tier_map 覆盖默认值。"""
    explicit = routing_cfg.get("tier_map") or {}
    use_ollama = routing_cfg.get("use_ollama", True)
    base = dict(DEFAULT_TIER_MAP_OLLAMA if use_ollama else DEFAULT_TIER_MAP_CLOUD)
    if explicit:
        base.update({str(k).upper().replace("C", "L") if str(k).startswith("C") else str(k).upper(): v for k, v in explicit.items()})

    if not use_ollama:
        return base

    from lib.adapters.integrations.ollama_routing import agent_supports_ollama, is_ollama_ready

    if not is_ollama_ready(config, data_dir=data_dir):
        return {k: (v if v != TIER_OLLAMA else TIER_FLASH) for k, v in base.items()}
    if agent_cfg and agent_types and not agent_supports_ollama(agent_cfg, agent_types):
        return {k: (v if v != TIER_OLLAMA else TIER_FLASH) for k, v in base.items()}
    return base


def map_tier_to_alias(
    tier: str,
    agent_cfg: dict,
    routing_cfg: Optional[dict] = None,
    *,
    config: Optional[dict] = None,
    data_dir: str = "",
    agent_types: Optional[dict] = None,
) -> str:
    cfg = routing_cfg or DEFAULT_SMART_ROUTING_CONFIG
    tier_map = resolve_effective_tier_map(
        cfg, config=config, data_dir=data_dir, agent_cfg=agent_cfg, agent_types=agent_types,
    )
    norm = tier.upper().replace("C", "L") if tier.upper().startswith("C") else tier.upper()
    alias = tier_map.get(norm, TIER_FLASH)

    if alias == TIER_PRO and not _pro_allowed(agent_cfg):
        # L3 无 Pro 许可：优先本机 Ollama，否则 flash
        from lib.adapters.integrations.ollama_routing import agent_supports_ollama, is_ollama_ready

        if (
            cfg.get("use_ollama", True)
            and is_ollama_ready(config, data_dir=data_dir)
            and agent_types
            and agent_supports_ollama(agent_cfg, agent_types)
        ):
            alias = TIER_OLLAMA
        else:
            alias = TIER_FLASH

    if alias == TIER_OLLAMA:
        from lib.adapters.integrations.ollama_routing import agent_supports_ollama, is_ollama_ready

        if not (
            cfg.get("use_ollama", True)
            and is_ollama_ready(config, data_dir=data_dir)
            and agent_types
            and agent_supports_ollama(agent_cfg, agent_types)
        ):
            alias = TIER_FLASH

    models = (agent_cfg or {}).get("models") or []
    if models and alias not in models:
        # 路由选了 ollama 但 agent 未声明 → 仍允许 ollama-local（全局 agent_types 有映射即可）
        if alias == TIER_OLLAMA and agent_types and agent_supports_ollama(agent_cfg, agent_types):
            return alias
        if TIER_FLASH in models:
            alias = TIER_FLASH
        elif TIER_OLLAMA in models:
            alias = TIER_OLLAMA
        else:
            alias = models[0]
    return alias


def suggest_model_alias(
    msg: Any,
    agent_cfg: dict,
    *,
    config: Optional[dict] = None,
    data_dir: str = "",
    primary_task_id: str = "",
    agent_types: Optional[dict] = None,
) -> Optional[dict[str, Any]]:
    if not smart_routing_enabled(config, agent_cfg):
        return None
    action = _action_dict(msg)
    if action.get("model_tier") in ("flash", "pro", "ollama", "local"):
        return None

    routing_cfg = load_smart_routing_config(config, agent_cfg)
    features = build_features(msg, data_dir=data_dir, primary_task_id=primary_task_id)
    tier = classify_complexity(features)
    alias = map_tier_to_alias(
        tier,
        agent_cfg,
        routing_cfg,
        config=config,
        data_dir=data_dir,
        agent_types=agent_types,
    )

    ollama_ready = False
    if routing_cfg.get("use_ollama", True):
        from lib.adapters.integrations.ollama_routing import is_ollama_ready

        ollama_ready = is_ollama_ready(config, data_dir=data_dir)

    gpu_step = None
    if alias == TIER_OLLAMA and config:
        from lib.adapters.integrations.ollama_routing import prepare_gpu_for_ollama_push

        gpu_step = prepare_gpu_for_ollama_push(config)

    return {
        "routing_engine": "mailbus-heuristic+ollama" if ollama_ready else "mailbus-heuristic",
        "complexity_tier": tier,
        "complexity_score": score_complexity(features),
        "model_alias": alias,
        "ollama_ready": ollama_ready,
        "gpu_prepare": gpu_step,
        "content_hash": _content_hash(features.get("text") or ""),
        "engine_version": ENGINE_VERSION,
        "msg_id": features.get("msg_id") or "",
    }


def log_routing_decision(
    data_dir: str,
    decision: dict[str, Any],
    *,
    agent_name: str = "",
    config: Optional[dict] = None,
) -> None:
    if not data_dir:
        return
    routing_cfg = load_smart_routing_config(config)
    if not routing_cfg.get("log_decisions", False):
        return
    from lib.infra.utils import _now_iso, jsonl_append

    log_dir = os.path.join(data_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    entry = {
        "timestamp": _now_iso(),
        "agent": agent_name,
        **{k: v for k, v in decision.items() if k != "text"},
    }
    jsonl_append(os.path.join(log_dir, "smart-routing.jsonl"), entry)


def attach_mailbus_routing(step_result: dict, routing: dict[str, Any]) -> dict:
    out = dict(step_result)
    ext = dict(out.get("extensions") or {})
    mb = dict(ext.get("mailbus") or {})
    mb["routing"] = dict(routing)
    ext["mailbus"] = mb
    out["extensions"] = ext
    return out
