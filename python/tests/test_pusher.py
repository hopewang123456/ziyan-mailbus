"""测试推送逻辑 (lib/pusher.py + agent_adapters)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.application.push.pusher import resolve_cli, resolve_cli_chain, _replace_msg_placeholder

TYPES = {
    "hermes": {"push": "legacy"},
    "hermes_profile": {"push": "legacy"},
    "openclaw": {"push": "legacy"},
    "opencode": {"push": "legacy"},
    "none": {"push": ""},
    "models": {
        "deepseek-chat": {
            "opencode": "--model deepseek/deepseek-chat",
        }
    },
}


def test_resolve_cli_hermes_profile():
    cfg = {"type": "hermes_profile", "profile": "agent-d"}
    cmd = resolve_cli(cfg, TYPES, agent_name="agent-d")
    assert "docker-agents-hermes-1" in cmd
    assert "--profile agent-d" in cmd
    assert "-q 'MSG'" in cmd
    print("  ✓ test_resolve_cli_hermes_profile")


def test_resolve_cli_openclaw():
    cfg = {"type": "openclaw", "agent": "main"}
    cmd = resolve_cli(cfg, TYPES, agent_name="agent-m")
    assert "openclaw agent" in cmd
    assert "--agent main" in cmd
    print("  ✓ test_resolve_cli_openclaw")


def test_resolve_cli_model_with_value():
    cfg = {"type": "opencode", "models": ["deepseek-chat"]}
    cmd = resolve_cli(cfg, TYPES, model_alias="deepseek-chat", agent_name="agent-i")
    assert "--model deepseek/deepseek-chat" in cmd
    print("  ✓ test_resolve_cli_model_with_value")


def test_resolve_cli_none_type():
    cfg = {"type": "none"}
    cmd = resolve_cli(cfg, TYPES)
    assert cmd == ""
    print("  ✓ test_resolve_cli_none_type")


def test_resolve_cli_chain_multi():
    types = {
        "opencode": {"push": "legacy"},
        "models": {
            "ds": {"opencode": "--model ds"},
            "qw": {"opencode": "--model qw"},
        },
    }
    cfg = {"type": "opencode", "models": ["ds", "qw"]}
    chain = resolve_cli_chain(cfg, types)
    assert len(chain) == 2
    assert "--model ds" in chain[0][0]
    assert "--model qw" in chain[1][0]
    print("  ✓ test_resolve_cli_chain_multi")


def test_replace_msg_placeholder_powershell_escapes_quotes():
    cmd = 'powershell -Command "claude -p \'MSG\'"'
    out = _replace_msg_placeholder(cmd, "it's a test")
    assert "it''s a test" in out
    print("  ✓ test_replace_msg_placeholder_powershell_escapes_quotes")


if __name__ == "__main__":
    test_resolve_cli_hermes_profile()
    test_resolve_cli_openclaw()
    test_resolve_cli_model_with_value()
    test_resolve_cli_none_type()
    test_resolve_cli_chain_multi()
    print(f"\n✓ 全部 {5} 个测试通过")
