"""E5 装配结果卡片 — 把 assemble.py 的公式变成看得见的表。

卡片口径（D2）：
- skills：三层（框架公共 / 组 / 私有）各自的清单 + 同名覆盖结果 + 最终生效列表；
- rules：框架在前、个人在后的分层与顺序；
- 人设：框架扫描 ∪ 用户添加（标注来源与路径存在性）；
- push：**实际会用到**的投递通道（容器/管线/工作目录/通道/模型——含兜底派生值）；
- 生效佐证：实例卡 ``last_smoke_ok_at``（E1 测试连接三段全绿时打点）。
"""
from __future__ import annotations

import os
from typing import Any

from lib.infra.utils import json_read

from .assemble import (
    layer_skills_for_agent,
    role_view,
    scanned_persona_files,
    skills_in_group,
    user_persona_files,
)

_FRAMEWORK_LAYER_TYPES = {"framework_skill"}


def _skill_brief(spec: dict[str, Any], layer: str) -> dict[str, Any]:
    return {
        "id": spec.get("id") or spec.get("path") or "",
        "type": spec.get("type") or "",
        "path": str(spec.get("path") or ""),
        "layer": layer,
    }


def _effective_push(data_dir: str, agent_id: str, agent_cfg: dict) -> dict[str, Any]:
    """运行时实际投递参数（含框架默认派生值——transport/override 语义的最终事实）。"""
    out: dict[str, Any] = {"agent": agent_id}
    atype = (agent_cfg.get("type") or "").strip()
    out["framework"] = atype
    try:
        from lib.adapters.frameworks import get_adapter

        adapter = get_adapter(atype)
        from lib.adapters.container.resolver import resolve_container

        container = ""
        svc = str(getattr(adapter, "container_service", "") or "").strip()
        if svc:
            container = resolve_container(agent_cfg, agent_id, svc)
        out["container"] = container
        if hasattr(adapter, "_profile"):
            try:
                out["profile"] = adapter._profile(agent_id, agent_cfg)  # type: ignore[attr-defined]
            except Exception:
                out["profile"] = agent_id
        from lib.adapters.frameworks import _push_cwd

        out["push_cwd"] = _push_cwd(agent_cfg) if svc or atype in ("codex", "opencode", "cline") else ""
    except Exception:
        out["container"] = ""
        out["push_cwd"] = ""
    models = agent_cfg.get("models") or []
    out["model"] = str(models[0]) if models else "(框架默认)"
    # 通道：agent-channels 默认合并后的实际取向
    try:
        from lib.core.a2a.agent_card_cache import enrich_agent_channels

        merged = enrich_agent_channels(agent_id, dict(agent_cfg))
        out["channel"] = "local_cli(file_bus)" if (merged.get("transport") == "local_cli") else "a2a+file_bus"
    except Exception:
        out["channel"] = ""
    return out


def assembly_card(data_dir: str, agent_id: str) -> dict[str, Any]:
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agent_cfg = (cfg.get("agents") or {}).get(agent_id)
    if not isinstance(agent_cfg, dict):
        raise ValueError(f"unknown agent: {agent_id}")

    view = role_view(agent_id, data_dir=data_dir)
    fw = agent_cfg.get("type") or view.get("framework") or ""

    # skills 三层（assemble 公式的分步展开）——实例卡直接上架的角色没有
    # transport/registry 记录（E4 新路径），此时技能层优雅为空而非报错。
    try:
        layered = layer_skills_for_agent(agent_id, fw) or []
    except Exception:
        layered = []
    framework_specs = [s for s in layered if s.get("type") in _FRAMEWORK_LAYER_TYPES]
    private_specs = [s for s in layered if s.get("type") not in _FRAMEWORK_LAYER_TYPES]
    group_map: dict[str, list[dict[str, Any]]] = {}
    for group in view.get("skill_groups") or []:
        group_map[group] = [
            _skill_brief(s, f"group:{group}") for s in (skills_in_group(group) or [])
        ]

    # 同名覆盖结果：私有/组 中与框架同 id 的项即「覆盖」
    fw_ids = {s.get("id") or s.get("path") for s in framework_specs}
    overrides: list[str] = []
    seen: dict[str, dict[str, Any]] = {}
    final: list[dict[str, Any]] = []
    for spec, layer in (
        [(s, "framework") for s in framework_specs]
        + [(s, g) for g, specs in group_map.items() for s in (skills_in_group(g) or [])]
        + [(s, "private") for s in private_specs]
    ):
        key = (spec.get("id") or spec.get("path") or "").strip()
        if not key:
            continue
        brief = _skill_brief(spec, layer)
        if key in seen:
            overrides.append(f"{key}: {seen[key]['layer']} → {layer}")
            seen[key] = brief
            final = [seen[k2["id"]] if k2["id"] == key else k2 for k2 in final]
        else:
            seen[key] = brief
            final.append(brief)

    rules = None
    try:
        from .assemble import assembled_rules_for_agent

        rules = assembled_rules_for_agent(agent_id, data_dir=data_dir)
    except Exception:
        rules = {"framework": [], "personal": [], "ordered": []}

    persona = {
        "scanned": [str(p) for p in (scanned_persona_files(agent_id, data_dir=data_dir) or [])],
        "user": [str(p) for p in (user_persona_files(agent_id, data_dir=data_dir) or [])],
        "persona_files_exist": all(
            os.path.isfile(str(p)) for p in (user_persona_files(agent_id, data_dir=data_dir) or [])
        ),
    }

    inst = (cfg.get("agent_instances") or {}).get(agent_cfg.get("instance_id") or "") or {}

    return {
        "agent_id": agent_id,
        "framework": fw,
        "instance_id": agent_cfg.get("instance_id") or "",
        "skills": {
            "framework": [_skill_brief(s, "framework") for s in framework_specs],
            "groups": group_map,
            "private": [_skill_brief(s, "private") for s in private_specs],
            "final": final,
            "overrides": overrides,
        },
        "rules": rules,
        "persona": persona,
        "push": _effective_push(data_dir, agent_id, agent_cfg),
        "last_smoke_ok_at": inst.get("last_smoke_ok_at") or "",
        "enabled": agent_cfg.get("enabled", True),
    }
