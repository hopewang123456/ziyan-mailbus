"""Role assembly — 三层 skills / rules / persona 按已拍板公式解析。

单一装配语义（配置页与运行时一致）：

    skills = 角色私有 ∪ skillgroup(多选) ∪ 框架公共
             同名覆盖：角色 > 组 > 框架
    rules  = 框架 + 个人；框架永远在前（法律在前）；无共享组
    人设   = 框架自动扫描 ∪ 用户添加；保存用户添加时 V1 校验路径存在

数据源分层（方案 B 收口）：

    ``role_view()`` 是唯一聚合入口，明确区分两套权威源，消费方不各自手搓读取：

    - **框架层 ``transport``**：framework / archetype（skills/rules 原始条目）
      权威 = ``access/transport/<id>/transport.json`` + Obsidian 人物索引 frontmatter
      读取 = :mod:`lib.adapters.config.agent_registry`（默认定位 ``MAILBUS_ROOT``）
    - **角色运行时层 ``role``**：paths / skill_groups / persona_files
      权威 = ``<data_dir>/config.json`` 的 ``agents.<id>``
      读取 = :func:`lib.infra.utils.json_read`（与 ``config_admin`` 同款，``data_dir`` 默认 ``MAILBUS_DATA_STR``）
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.infra.constants import MAILBUS_DATA_STR, MAILBUS_SKILLGROUP_ROOT
from lib.infra.utils import json_read

from .agent_registry import get_agent, layer_skills_for_agent
from .rules_registry import rule_paths_for_agent

# 人设默认文件名（框架自动扫描这些）
PERSONA_DEFAULT_NAMES: tuple[str, ...] = ("SOUL.md", "CLAUDE.md", "AGENTS.md")

# 框架公共 skills 层（全员加载）；其余为角色私有层
_FRAMEWORK_LAYER_TYPES = frozenset({"framework_skill", "shared_skill"})


# ── 单一聚合入口 ──────────────────────────────────────────────────────────


def _data_dir(data_dir: Path | str | None) -> Path:
    """config.json 定位目录：显式参数 > ``MAILBUS_DATA_STR``（默认 ``MAILBUS_ROOT/store``）。"""
    return Path(data_dir) if data_dir is not None else Path(MAILBUS_DATA_STR)


def role_view(agent_id: str, *, data_dir: Path | str | None = None) -> dict[str, Any]:
    """聚合「框架层 + 角色运行时层」两套权威源，返回角色装配输入视图。

    返回字段：
      - ``transport`` / ``framework`` / ``archetype``：框架层（transport + profile）
      - ``role`` / ``paths`` / ``skill_groups`` / ``persona_files``：角色运行时层（config.json agents）
    """
    transport = get_agent(agent_id) or {}
    cfg = json_read(str(_data_dir(data_dir) / "config.json"), {})
    if not isinstance(cfg, dict):
        cfg = {}
    role = (cfg.get("agents") or {}).get(agent_id)
    role = role if isinstance(role, dict) else {}

    paths = role.get("paths") if isinstance(role.get("paths"), dict) else {}
    return {
        "agent_id": agent_id,
        "framework": transport.get("framework") or role.get("type") or "",
        "archetype": transport.get("archetype") or role.get("archetype") or "",
        "transport": transport,  # 框架层（transport + profile）
        "role": role,  # 角色运行时层（config.json agents）
        "paths": paths,
        "skill_groups": [
            g for g in (role.get("skill_groups") or []) if isinstance(g, str) and g.strip()
        ],
        "persona_files": [
            f for f in (role.get("persona_files") or []) if isinstance(f, str) and f.strip()
        ],
    }


# ── skillgroup ────────────────────────────────────────────────────────────


def skillgroup_root() -> Path:
    """skillgroup 根：``MAILBUS_SKILLGROUP_ROOT``（env 覆盖 > 仓库 ``skills/skillgroup/``）。"""
    return MAILBUS_SKILLGROUP_ROOT


def list_skill_groups() -> list[str]:
    """返回 skillgroup 根下所有组名（一级子目录）。"""
    root = skillgroup_root()
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))


def _spec_from_skill_path(skill_path: Path, group: str) -> dict[str, Any]:
    name = skill_path.stem if skill_path.suffix == ".md" else skill_path.name
    rel = skill_path.as_posix()
    if skill_path.is_dir():
        rel = (skill_path / "SKILL.md").as_posix() if (skill_path / "SKILL.md").is_file() else rel
    return {
        "id": name,
        "path": rel,
        "type": "skillgroup",
        "layer": "SG",
        "skillgroup": group,
        "always": True,
    }


def skills_in_group(group: str) -> list[dict[str, Any]]:
    """一个组内所有技能（子目录或 ``*.md``），按名称稳定排序。"""
    root = skillgroup_root() / group
    if not root.is_dir():
        return []
    specs: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir() or child.suffix == ".md":
            specs.append(_spec_from_skill_path(child, group))
    return specs


# ── 装配解析 ──────────────────────────────────────────────────────────────


def _merge_by_id(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同名（id）覆盖，保留首现顺序；后出现者覆盖先出现者。"""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for spec in specs:
        key = (spec.get("id") or spec.get("path") or "").strip()
        if not key:
            continue
        if key not in merged:
            order.append(key)
        merged[key] = spec
    return [merged[k] for k in order]


def assembled_skills_for_agent(
    agent_id: str,
    framework: str | None = None,
    *,
    data_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """三层 skills 合并（有序）：框架公共 → 组 → 私有；同名覆盖 私有 > 组 > 框架。"""
    view = role_view(agent_id, data_dir=data_dir)
    fw = framework or view["framework"]

    layered = layer_skills_for_agent(agent_id, fw)
    framework_specs = [s for s in layered if s.get("type") in _FRAMEWORK_LAYER_TYPES]
    private_specs = [s for s in layered if s.get("type") not in _FRAMEWORK_LAYER_TYPES]

    group_specs: list[dict[str, Any]] = []
    for group in view["skill_groups"]:
        group_specs.extend(skills_in_group(group))

    # 框架 → 组 → 私有：后者覆盖同名前者
    return _merge_by_id(framework_specs + group_specs + private_specs)


def assembled_rules_for_agent(
    agent_id: str, *, data_dir: Path | str | None = None
) -> dict[str, Any]:
    """rules 拼接顺序：框架/公共在前，个人在后（法律在前）。返回分层 + 有序列表。"""
    rels = rule_paths_for_agent(agent_id)
    framework: list[str] = []
    personal: list[str] = []
    for rel in rels:
        norm = rel.replace("\\", "/")
        if (
            "/0111-common/" in norm
            or "/0112-frameworks/" in norm
            or "/rules/common/" in norm
            or "/rules/frameworks/" in norm
            or norm.endswith("agent-universal")
        ):
            framework.append(norm)
        else:
            personal.append(norm)
    return {"framework": framework, "personal": personal, "ordered": framework + personal}


# ── 人设 ─────────────────────────────────────────────────────────────────


def persona_dir(agent_id: str, *, data_dir: Path | str | None = None) -> str:
    view = role_view(agent_id, data_dir=data_dir)
    return str((view["paths"].get("persona") or "").strip())


def scanned_persona_files(
    agent_id: str, *, data_dir: Path | str | None = None
) -> list[str]:
    """框架自动扫描：persona 目录下默认人设文件（SOUL.md/CLAUDE.md/AGENTS.md 等）。"""
    d = persona_dir(agent_id, data_dir=data_dir)
    if not d:
        return []
    root = Path(d)
    if not root.is_dir():
        return []
    found: list[str] = []
    for name in PERSONA_DEFAULT_NAMES:
        p = root / name
        if p.is_file():
            found.append(p.as_posix())
    return found


def user_persona_files(
    agent_id: str, *, data_dir: Path | str | None = None
) -> list[str]:
    """用户添加的人设文件（config.json ``agents.<id>.persona_files[]``）。"""
    view = role_view(agent_id, data_dir=data_dir)
    return view["persona_files"]


def assembled_persona_for_agent(
    agent_id: str, *, data_dir: Path | str | None = None
) -> dict[str, Any]:
    """人设 = 框架扫描 ∪ 用户添加（并集，去重保序）。"""
    scan = scanned_persona_files(agent_id, data_dir=data_dir)
    user = user_persona_files(agent_id, data_dir=data_dir)
    all_files: list[str] = []
    seen: set[str] = set()
    for p in scan + user:
        if p not in seen:
            seen.add(p)
            all_files.append(p)
    return {"scan": scan, "user": user, "all": all_files}


def verify_persona_files(files: list[str]) -> list[dict[str, Any]]:
    """V1 校验：人设文件是否存在（不探活）。返回缺失列表。"""
    missing: list[dict[str, Any]] = []
    for f in files:
        p = Path(str(f))
        if not p.is_file():
            missing.append({"path": str(f), "exists": False})
    return missing
