"""model_router / complexity_router / ollama 单元测试"""
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.model_router import is_no_llm_notice, pick_model_alias, TIER_FLASH, TIER_OLLAMA
from lib.complexity_router import (
    attach_mailbus_routing,
    classify_complexity,
    load_smart_routing_config,
    map_tier_to_alias,
    resolve_effective_tier_map,
    score_complexity,
    smart_routing_enabled,
    suggest_model_alias,
)


AGENT_TYPES = {
    "models": {
        "deepseek-flash": {"hermes_profile": "--model deepseek-chat"},
        "ollama-local": {"hermes_profile": "--provider ollama --model {model}"},
    }
}


def test_no_llm_remind():
    assert is_no_llm_notice({"id": "remind-123", "type": "notice", "content": "x"})


def test_smart_routing_disabled():
    cfg = {"smart_routing": {"enabled": False}, "agent_types": AGENT_TYPES}
    assert not smart_routing_enabled(cfg)
    alias = pick_model_alias(
        {"type": "task", "content": "x" * 2000, "id": "m1"},
        "lingzhao", {"models": ["deepseek-flash"], "type": "hermes_profile"},
        config=cfg,
    )
    assert alias == TIER_FLASH


@patch("lib.ollama_routing.is_ollama_ready", return_value=True)
def test_ollama_tier_l1(mock_ready):
    cfg = {
        "smart_routing": {"enabled": True, "use_ollama": True, "log_decisions": False},
        "agent_types": AGENT_TYPES,
    }
    agent = {"type": "hermes_profile", "models": ["deepseek-flash"]}
    routing = {}
    alias = pick_model_alias(
        {"type": "task", "id": "m1", "content": "常规开发任务说明"},
        "lingzhao", agent, config=cfg, routing_out=routing,
    )
    assert alias == TIER_OLLAMA
    assert routing.get("ollama_ready") is True
    mock_ready.assert_called()


@patch("lib.ollama_routing.is_ollama_ready", return_value=False)
def test_ollama_offline_fallback_flash(mock_ready):
    cfg = {
        "smart_routing": {"enabled": True, "use_ollama": True},
        "agent_types": AGENT_TYPES,
    }
    tier_map = resolve_effective_tier_map(
        cfg["smart_routing"], config=cfg,
        agent_cfg={"type": "hermes_profile"}, agent_types=AGENT_TYPES,
    )
    assert tier_map["L1"] == TIER_FLASH


@patch("lib.ollama_routing.is_ollama_ready", return_value=True)
def test_l3_without_pro_uses_ollama(mock_ready):
    cfg = {"smart_routing": {"enabled": True, "use_ollama": True}, "agent_types": AGENT_TYPES}
    alias = map_tier_to_alias(
        "L3", {"type": "hermes_profile", "models": ["deepseek-flash", "deepseek-pro"]},
        cfg["smart_routing"], config=cfg, agent_types=AGENT_TYPES,
    )
    assert alias == TIER_OLLAMA


def test_simple_notice_low_score():
    feats = {"content_length": 50, "has_simple_keyword": True, "has_code_block": False, "msg_type": "notice"}
    assert score_complexity(feats) == 0
    assert classify_complexity(feats) == "L0"


def test_attach_mailbus_routing():
    out = attach_mailbus_routing({"summary": "ok"}, {"complexity_tier": "L1", "model_alias": "ollama-local"})
    assert out["extensions"]["mailbus"]["routing"]["model_alias"] == "ollama-local"


def test_log_routing_jsonl():
    from lib.complexity_router import log_routing_decision

    with tempfile.TemporaryDirectory() as tmp:
        log_routing_decision(
            tmp,
            {"complexity_tier": "L1", "model_alias": "ollama-local"},
            agent_name="lingzhao",
            config={"smart_routing": {"log_decisions": True}},
        )
        assert os.path.isfile(os.path.join(tmp, "logs", "smart-routing.jsonl"))


if __name__ == "__main__":
    test_no_llm_remind()
    test_smart_routing_disabled()
    test_ollama_tier_l1()
    test_ollama_offline_fallback_flash()
    test_l3_without_pro_uses_ollama()
    test_simple_notice_low_score()
    test_attach_mailbus_routing()
    test_log_routing_jsonl()
    print("\n  all model_router tests passed")
