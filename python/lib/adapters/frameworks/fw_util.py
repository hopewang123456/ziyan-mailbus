"""Adapter 共用工具 — 模型 flag 解析 / cwd / shell 转义。

消费方：各家族 Adapter 文件、direct_push；registry re-export 保持既有 API。
"""
from __future__ import annotations

import os
from typing import Optional


def model_flag(
    agent_cfg: dict,
    agent_types: dict,
    atype: str,
    model_alias: Optional[str],
    *,
    data_dir: str = "",
    config: dict | None = None,
) -> str:
    models_map = agent_types.get("models", {})
    agent_models = agent_cfg.get("models", [])
    if model_alias == "ollama-local":
        from lib.adapters.llm_routing.ollama_routing import ollama_model_flag
        from lib.infra.push_context import get_push_context

        ctx = get_push_context()
        flag = ollama_model_flag(
            atype,
            config=ctx.get("config"),
            data_dir=ctx.get("data_dir") or "",
            agent_types=agent_types,
        )
        if flag:
            return flag
        model_alias = "deepseek-flash"
    # 路由选了 pro 但 agent 未装备 → 回落 flash，避免 Hermes profile 默认走 v4-pro
    if model_alias and model_alias not in agent_models and agent_models:
        model_alias = agent_models[0]
    if not model_alias:
        model_alias = agent_models[0] if agent_models else None
    if model_alias and model_alias in models_map:
        return models_map[model_alias].get(atype, "") or ""
    return ""


def provider_flag(agent_cfg: dict, agent_types: dict, atype: str, model_alias: Optional[str]) -> str:
    final = (agent_cfg.get("provider") or "").strip()
    if final:
        return final
    models_map = agent_types.get("models", {})
    agent_models = agent_cfg.get("models", [])
    if model_alias and model_alias not in agent_models and agent_models:
        model_alias = agent_models[0]
    if not model_alias:
        model_alias = agent_models[0] if agent_models else None
    if model_alias and model_alias in models_map:
        return models_map[model_alias].get(atype, "") or ""
    return ""


def _join(*parts: str) -> str:
    return " ".join(p for p in parts if p).strip()


def _flag_value(raw: str, *prefixes: str) -> str:
    """从 '--provider foo' / '-P foo' 提取值。"""
    text = (raw or "").strip()
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _push_cwd(agent_cfg: dict, default: str = "/mailbus/store") -> str:
    push = agent_cfg.get("push") or {}
    raw = (push.get("cwd") or agent_cfg.get("cwd") or default).strip()
    # 净化模板占位路径（/path/to/xxx 等），防止 docker exec 内 cd 失败
    if raw.startswith("/path/"):
        return default
    return raw


# Cline / OpenCode 与 Hermes / OpenClaw 推送语义不同：
# - Hermes/OpenClaw: -q/--message 单次查询，notice 可 auto_ack
# - Cline/OpenCode:  positional prompt + run 子命令，须等 CLI 落盘 msg-results，永不 auto_ack
# Docker compose 服务名 → 推荐 agent type（派生自 FRAMEWORKS.docker_services 反转）


def shlex_quote(s: str) -> str:
    """Shell 单引号转义（供 docker exec bash -lc 使用）。"""
    if not s:
        return "''"
    return "'" + s.replace("'", "'\"'\"'") + "'"
