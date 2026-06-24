"""model_router 单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.model_router import is_no_llm_notice, pick_model_alias, TIER_FLASH, TIER_PRO


def test_no_llm_remind():
    assert is_no_llm_notice({"id": "remind-123", "type": "notice", "content": "x"})
    print("  ok test_no_llm_remind")


def test_no_llm_timeout_notice():
    assert is_no_llm_notice({
        "id": "n1", "type": "notice", "content": "⚠️ 超时提醒（第1次）",
    })
    print("  ok test_no_llm_timeout_notice")


def test_flash_for_normal_task():
    alias = pick_model_alias(
        {"type": "task", "priority": "normal", "content": "日常开发"},
        "dali", {"models": ["deepseek-flash"]},
    )
    assert alias == TIER_FLASH
    print("  ok test_flash_for_normal_task")


def test_flash_for_primary_urgent():
    alias = pick_model_alias(
        {"type": "task", "priority": "urgent", "content": "【mailbus-scheduler-validation-20260616】"},
        "lingzhao", {"models": ["deepseek-flash"]},
        primary_task_id="mailbus-scheduler-validation-20260616",
    )
    assert alias == TIER_FLASH
    print("  ok test_flash_for_primary_urgent")


def test_pro_only_when_explicit_and_allowed():
    alias = pick_model_alias(
        {"type": "task", "priority": "urgent", "content": "x", "action": {"model_tier": "pro"}},
        "lingzhao", {"models": ["deepseek-flash"]},
    )
    assert alias == TIER_FLASH
    alias2 = pick_model_alias(
        {"type": "task", "content": "x", "action": {"model_tier": "pro"}},
        "lingzhao", {"models": ["deepseek-flash", "deepseek-pro"]},
    )
    assert alias2 == TIER_FLASH  # 未设 MAILBUS_ALLOW_PRO
    print("  ok test_pro_only_when_explicit_and_allowed")


def test_no_llm_execute_false_notice():
    assert is_no_llm_notice({
        "id": "n-sys", "type": "notice", "from": "mailbus",
        "content": "普通系统通知", "action": {"execute": False},
    })
    assert not is_no_llm_notice({
        "id": "n-test", "type": "notice", "from": "lingzhao",
        "content": "test message", "action": {"execute": False},
    })
    print("  ok test_no_llm_execute_false_notice")


def test_no_llm_mailbus_notice():
    assert is_no_llm_notice({
        "id": "msg-1", "type": "notice", "from": "mailbus",
        "content": "【game-stellar】修复完成",
    })
    print("  ok test_no_llm_mailbus_notice")


if __name__ == "__main__":
    test_no_llm_remind()
    test_no_llm_timeout_notice()
    test_no_llm_execute_false_notice()
    test_no_llm_mailbus_notice()
    test_flash_for_normal_task()
    test_flash_for_primary_urgent()
    test_pro_only_when_explicit_and_allowed()
    print("\n  all model_router tests passed")
