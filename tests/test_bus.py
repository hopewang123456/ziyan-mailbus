"""
bus.py 单元测试 — CLI 命令核心函数

覆盖：load_config / save_config / _find_config / _push_queue / cmd_init
"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bus import load_config, save_config
from lib.constants import DEFAULT_ACK_TIMEOUT


def test_load_config_defaults():
    """加载不存在的配置返回默认值"""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(os.path.join(tmp, "nonexistent.json"))
        assert cfg["project"] == "ziyan-mailbus"
        assert cfg["ack_timeout"] == DEFAULT_ACK_TIMEOUT
        assert cfg["max_retries"] == 3
        assert cfg["agents"] == {}


def test_load_config_merged():
    """加载部分配置，缺失字段用默认值填充"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "config.json")
        with open(path, "w") as f:
            json.dump({"project": "custom", "agents": {"test": {"name": "t"}}}, f)
        cfg = load_config(path)
        assert cfg["project"] == "custom"
        assert cfg["ack_timeout"] == DEFAULT_ACK_TIMEOUT
        assert cfg["agents"]["test"]["name"] == "t"


def test_save_and_load_roundtrip():
    """保存后再加载，数据一致"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "config.json")
        original = {
            "project": "ziyan-mailbus",
            "version": "1.0.0",
            "data_dir": tmp,
            "ack_timeout": 15,
            "max_retries": 5,
            "agents": {"lingxiao": {"name": "灵霄", "type": "opencode"}},
        }
        save_config(path, original)
        loaded = load_config(path)
        assert loaded["ack_timeout"] == 15
        assert loaded["agents"]["lingxiao"]["name"] == "灵霄"


def test_load_config_bad_json():
    """损坏的 JSON 返回默认值（不抛异常）"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "config.json")
        with open(path, "w") as f:
            f.write("{bad json}")
        cfg = load_config(path)
        assert cfg["project"] == "ziyan-mailbus"


def test_get_system_message():
    """get_system_message 返回正确的结构"""
    from lib.commands import get_system_message
    msg = get_system_message("test_agent")
    assert msg["to"] == "test_agent"
    assert msg["from"] == "mailbus"
    assert "inbox_location" in msg["system_info"]
    assert "bus_cli_location" in msg["system_info"]


def test_cmd_init_fresh_thirteen_agents():
    """bus.py init --fresh 应生成 13 agents + workflows registry。"""
    import json
    import tempfile
    from lib.constants import MAILBUS_ROOT
    from lib.init_store import run_init_store

    with tempfile.TemporaryDirectory() as tmp:
        rc = run_init_store(tmp, fresh=True, mail_root=MAILBUS_ROOT, quiet=True)
        assert rc == 0
        cfg = json.load(open(os.path.join(tmp, "config.json"), encoding="utf-8"))
        assert len(cfg.get("agents") or {}) == 13
        reg = json.load(open(os.path.join(tmp, "workflows", "registry.json"), encoding="utf-8"))
        assert len(reg.get("workflows") or {}) >= 6


if __name__ == "__main__":
    test_load_config_defaults()
    print("✅ test_load_config_defaults")
    test_load_config_merged()
    print("✅ test_load_config_merged")
    test_save_and_load_roundtrip()
    print("✅ test_save_and_load_roundtrip")
    test_load_config_bad_json()
    print("✅ test_load_config_bad_json")
    test_get_system_message()
    print("✅ test_get_system_message")
    test_cmd_init_fresh_thirteen_agents()
    print("✅ test_cmd_init_fresh_thirteen_agents")
    print("\n🎉 全部通过")
