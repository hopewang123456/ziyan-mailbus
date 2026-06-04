"""
ziyan-mailbus 配置校验 — JSON Schema

所有 config.json 在 load_config() 后必须经过此校验，
确保字段完整、类型正确、不包含未知字段。
"""

import json
import os
from typing import Optional

# ── Config JSON Schema ────────────────────────────────────────────────────

CONFIG_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ziyan-mailbus config",
    "type": "object",
    "required": ["project", "version", "data_dir", "ack_timeout", "max_retries",
                  "archive_days", "archive_max_messages", "agents"],
    "properties": {
        "project": {"type": "string", "description": "项目名称"},
        "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+", "description": "语义化版本号"},
        "data_dir": {"type": "string", "description": "数据存储目录"},
        "ack_timeout": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
        "max_retries": {"type": "integer", "minimum": 0, "maximum": 20, "default": 3},
        "archive_days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 3},
        "archive_max_messages": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 300},
        "poll_interval": {"type": "integer", "minimum": 1, "default": 15},
        "heartbeat_interval": {"type": "integer", "minimum": 10, "default": 60},
        "token": {"type": "string", "description": "API 服务认证 token"},
        "agents": {
            "type": "object",
            "description": "注册的 agent 列表",
            "patternProperties": {
                "^[a-zA-Z][a-zA-Z0-9_-]*$": {
                    "type": "object",
                    "required": ["type"],
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["hermes", "hermes_profile", "openclaw", "cline", "opencode", "none"]
                        },
                        "role": {"type": "string", "maxLength": 500},
                        "profile": {"type": "string"},
                        "agent": {"type": "string"},
                        "agent_id": {"type": "string"},
                        "provider": {"type": "string"},
                        "models": {
                            "type": "array",
                            "items": {"type": "string"},
                            "uniqueItems": True
                        },
                        "webhook_url": {"type": "string", "format": "uri",
                                        "description": "Webhook 推送地址（可选）"},
                        "webhook_secret": {"type": "string",
                                           "description": "Webhook 签名密钥（可选）"},
                    },
                    "additionalProperties": False
                }
            },
            "additionalProperties": False
        }
    },
    "additionalProperties": False
}


def validate_config(config: dict, config_path: str = "") -> list:
    """
    校验配置字典，返回错误信息列表。
    空列表 = 校验通过。
    """
    errors = []

    # ── 必需字段检查 ──
    required = CONFIG_SCHEMA["required"]
    for field in required:
        if field not in config:
            errors.append(f"缺少必需字段: {field}")

    if errors:
        return errors  # 缺字段就不继续往下检了，避免级联报错

    # ── 类型/范围检查 ──
    type_checks = [
        ("project", str),
        ("version", str),
        ("data_dir", str),
        ("ack_timeout", int),
        ("max_retries", int),
        ("archive_days", int),
        ("archive_max_messages", int),
    ]
    for field, expected_type in type_checks:
        val = config.get(field)
        if not isinstance(val, expected_type):
            errors.append(f"{field}: 期望 {expected_type.__name__} 类型，得到 {type(val).__name__} ({val!r})")

    # ── 范围检查 ──
    range_checks = [
        ("ack_timeout", 1, 300),
        ("max_retries", 0, 20),
        ("archive_days", 1, 365),
        ("archive_max_messages", 1, 10000),
    ]
    for field, lo, hi in range_checks:
        val = config.get(field)
        if isinstance(val, int) and (val < lo or val > hi):
            errors.append(f"{field}: 值 {val} 超出范围 [{lo}, {hi}]")

    # ── version 格式 ──
    version = config.get("version", "")
    if not isinstance(version, str) or not __import__("re").match(r"^\d+\.\d+\.\d+", version):
        errors.append(f"version: 不是有效的语义化版本号 ({version!r})")

    # ── agents 校验 ──
    agents = config.get("agents", {})
    if not isinstance(agents, dict):
        errors.append("agents: 期望 object 类型")
    else:
        for name, cfg in agents.items():
            if not isinstance(name, str) or not __import__("re").match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", name):
                errors.append(f"agents.{name}: agent 名称格式不合法")
            if not isinstance(cfg, dict):
                errors.append(f"agents.{name}: 期望 object 类型")
                continue
            if "type" not in cfg:
                errors.append(f"agents.{name}: 缺少必需字段 type")
            elif cfg["type"] not in ("hermes", "hermes_profile", "openclaw", "cline", "opencode", "none"):
                errors.append(f"agents.{name}.type: 不支持的 agent 类型 ({cfg['type']})")
            # 检查未知字段
            allowed = {"type", "role", "profile", "agent", "agent_id", "provider",
                       "models", "webhook_url", "webhook_secret",
                       "name", "inbox", "profile_paths", "launch"}
            extra = set(cfg.keys()) - allowed
            if extra:
                errors.append(f"agents.{name}: 未知字段 {extra}")

    return errors


def validate_config_file(config_path: str) -> tuple:
    """
    校验配置文件，返回 (is_valid: bool, errors: list, config: dict)
    """
    if not os.path.isfile(config_path):
        return False, [f"配置文件不存在: {config_path}"], {}

    try:
        with open(config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"JSON 解析错误: {e}"], {}

    if not isinstance(config, dict):
        return False, ["配置文件顶层必须是 object"], config

    errors = validate_config(config, config_path)
    return (len(errors) == 0), errors, config
