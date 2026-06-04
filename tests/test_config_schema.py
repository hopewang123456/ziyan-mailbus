"""
ziyan-mailbus 配置校验测试
"""
import os
import sys
import json
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.config_schema import validate_config, validate_config_file


def _valid_config() -> dict:
    return {
        "project": "ziyan-mailbus",
        "version": "1.0.0",
        "data_dir": "/tmp/store",
        "ack_timeout": 30,
        "max_retries": 3,
        "archive_days": 3,
        "archive_max_messages": 300,
        "agents": {
            "lingxiao": {
                "type": "cline",
                "role": "技术负责人",
                "models": ["fast", "default"],
            }
        },
    }


def test_valid_config():
    """合法配置应无错误"""
    errors = validate_config(_valid_config())
    assert errors == [], f"期望无错误，得到: {errors}"


def test_missing_required():
    """缺少必需字段应报错"""
    cfg = _valid_config()
    del cfg["project"]
    errors = validate_config(cfg)
    assert len(errors) > 0
    assert any("project" in e for e in errors)


def test_wrong_type():
    """类型错误应报错"""
    cfg = _valid_config()
    cfg["ack_timeout"] = "30"  # 字符串而非整数
    errors = validate_config(cfg)
    assert any("ack_timeout" in e for e in errors)


def test_out_of_range():
    """超出范围应报错"""
    cfg = _valid_config()
    cfg["max_retries"] = 999
    errors = validate_config(cfg)
    assert any("max_retries" in e for e in errors)


def test_bad_version():
    """版本号格式错误应报错"""
    cfg = _valid_config()
    cfg["version"] = "abc"
    errors = validate_config(cfg)
    assert any("version" in e for e in errors)


def test_invalid_agent_type():
    """不支持的 agent 类型应报错"""
    cfg = _valid_config()
    cfg["agents"]["test"] = {"type": "unknown_type"}
    errors = validate_config(cfg)
    assert any("type" in e and "unknown_type" in e for e in errors)


def test_agent_extra_fields():
    """agent 配置中的未知字段应报错"""
    cfg = _valid_config()
    cfg["agents"]["test"] = {"type": "cline", "unknown_field": "xxx"}
    errors = validate_config(cfg)
    assert any("未知字段" in e for e in errors)


def test_empty_agents():
    """空 agents 对象是合法的"""
    cfg = _valid_config()
    cfg["agents"] = {}
    errors = validate_config(cfg)
    assert errors == []


def test_validate_config_file_not_found():
    """不存在的文件应返回错误"""
    valid, errors, cfg = validate_config_file("/tmp/nonexistent_config_xxx.json")
    assert not valid
    assert len(errors) > 0


def test_validate_config_file_bad_json():
    """非法 JSON 应返回错误"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not json")
        path = f.name
    valid, errors, cfg = validate_config_file(path)
    assert not valid
    assert any("JSON" in e for e in errors)
    os.unlink(path)


def test_validate_config_file_valid():
    """合法配置文件应通过"""
    cfg = _valid_config()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(cfg, f)
        path = f.name
    valid, errors, cfg = validate_config_file(path)
    assert valid, f"期望通过，得到: {errors}"
    os.unlink(path)
