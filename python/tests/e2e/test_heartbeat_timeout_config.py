"""心跳超时：默认对齐设计 90s，且装配层注入的配置要真正生效。"""

from __future__ import annotations

from datetime import timedelta

from mailbus.core.agents import rules


def test_heartbeat_timeout_defaults_to_design_90s():
    assert rules.HEARTBEAT_TIMEOUT == timedelta(seconds=90)


def test_configure_heartbeat_timeout_takes_effect_and_falls_back():
    original = rules.heartbeat_timeout()
    try:
        rules.configure_heartbeat_timeout(30)
        assert rules.heartbeat_timeout() == timedelta(seconds=30)
        # 非正值回落默认，避免把在线窗口配成 0/负数
        rules.configure_heartbeat_timeout(0)
        assert rules.heartbeat_timeout() == rules.HEARTBEAT_TIMEOUT
    finally:
        rules.configure_heartbeat_timeout(original.total_seconds())
