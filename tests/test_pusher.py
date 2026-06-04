"""测试推送逻辑 (lib/pusher.py)"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.pusher import resolve_cli, resolve_cli_chain


def test_resolve_cli_basic():
    """基础替换：无占位符"""
    cfg = {"type": "hermes"}
    types = {"hermes": {"push": "hermes chat -q 'MSG' -Q"}}
    cmd = resolve_cli(cfg, types)
    assert cmd == "hermes chat -q 'MSG' -Q"
    print("  ✓ test_resolve_cli_basic")


def test_resolve_cli_profile():
    """PROFILE 占位符替换"""
    cfg = {"type": "hermes_profile", "profile": "lingxi"}
    types = {"hermes_profile": {"push": "hermes chat -q 'MSG' -Q --profile PROFILE"}}
    cmd = resolve_cli(cfg, types)
    assert cmd == "hermes chat -q 'MSG' -Q --profile lingxi"
    print("  ✓ test_resolve_cli_profile")


def test_resolve_cli_agent():
    """AGENT 占位符替换"""
    cfg = {"type": "openclaw", "agent": "main"}
    types = {"openclaw": {"push": "openclaw agent --local --agent AGENT --message 'MSG'"}}
    cmd = resolve_cli(cfg, types)
    assert "AGENT" not in cmd
    assert "main" in cmd
    print("  ✓ test_resolve_cli_agent")


def test_resolve_cli_model_with_value():
    """MODEL 占位符替换（有模型配置）"""
    types = {
        "opencode": {"push": "opencode run 'MSG' MODEL"},
        "models": {
            "deepseek-chat": {"opencode": "--model deepseek/deepseek-chat"}
        }
    }
    cfg = {"type": "opencode", "models": ["deepseek-chat"]}
    cmd = resolve_cli(cfg, types, model_alias="deepseek-chat")
    assert "--model deepseek/deepseek-chat" in cmd
    print("  ✓ test_resolve_cli_model_with_value")


def test_resolve_cli_model_without_value():
    """MODEL 占位符替换（无模型配置时自动消除）"""
    types = {"opencode": {"push": "opencode run 'MSG' --model MODEL"}}
    cfg = {"type": "opencode"}
    cmd = resolve_cli(cfg, types)
    assert "--model MODEL" not in cmd
    assert cmd == "opencode run 'MSG'"
    print("  ✓ test_resolve_cli_model_without_value")


def test_resolve_cli_none_type():
    """none 类型返回空"""
    cfg = {"type": "none"}
    types = {"none": {"push": ""}}
    cmd = resolve_cli(cfg, types)
    assert cmd == ""
    print("  ✓ test_resolve_cli_none_type")


def test_resolve_cli_chain_single():
    """resolve_cli_chain 单模型"""
    cfg = {"type": "hermes"}
    types = {"hermes": {"push": "hermes chat -q 'MSG' -Q"}}
    chain = resolve_cli_chain(cfg, types)
    assert len(chain) == 1
    assert chain[0][1] is None  # 无 models 时 alias 为 None
    print("  ✓ test_resolve_cli_chain_single")


def test_resolve_cli_chain_multi():
    """resolve_cli_chain 多模型 fallback"""
    types = {
        "opencode": {"push": "opencode run 'MSG' MODEL"},
        "models": {
            "ds": {"opencode": "--model ds"},
            "qw": {"opencode": "--model qw"},
        }
    }
    cfg = {"type": "opencode", "models": ["ds", "qw"]}
    chain = resolve_cli_chain(cfg, types)
    assert len(chain) == 2
    assert chain[0][1] == "ds"
    assert chain[1][1] == "qw"
    assert "--model ds" in chain[0][0]
    assert "--model qw" in chain[1][0]
    print("  ✓ test_resolve_cli_chain_multi")


def test_resolve_cli_chain_empty_models():
    """models 为空列表时返回单条命令"""
    cfg = {"type": "hermes"}
    types = {"hermes": {"push": "hermes chat -q 'MSG' -Q"}}
    chain = resolve_cli_chain(cfg, types)
    assert len(chain) == 1
    print("  ✓ test_resolve_cli_chain_empty_models")


if __name__ == "__main__":
    test_resolve_cli_basic()
    test_resolve_cli_profile()
    test_resolve_cli_agent()
    test_resolve_cli_model_with_value()
    test_resolve_cli_model_without_value()
    test_resolve_cli_none_type()
    test_resolve_cli_chain_single()
    test_resolve_cli_chain_multi()
    test_resolve_cli_chain_empty_models()
    print(f"\n✓ 全部 {9} 个测试通过")
