"""Agent instance vs role cards — data shape helpers (clarify round-2 SoT).

Config page → ``agent_instances`` (few).
Roster → ``agents`` roles with ``instance_id`` pointing at parent instance.

运行环境字段（type/run_target/install_path/host/custom_paths/distro/enabled）唯一 SoT
在实例；角色只保留 ``instance_id`` 指针 + 角色个体字段。
"""

from __future__ import annotations

import hashlib
from typing import Any


def _instance_key(atype: str, run_target: str, install_path: str, host: str, port: Any, distro: str = "auto") -> str:
    raw = f"{atype}|{run_target}|{install_path}|{host}|{port}|{distro}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    safe = (atype or "agent").replace("_", "-")
    return f"inst-{safe}-{digest}"


def _norm_host(host: str) -> str:
    h = (host or "").strip()
    if not h or h in ("localhost", "0.0.0.0", "::1"):
        return "127.0.0.1"
    return h


def _norm_path(path: str) -> str:
    return (path or "").strip().replace("/", "\\").rstrip("\\").lower()


def _norm_distro(distro: str) -> str:
    """distro 归一：仅 wsl/linux 有意义；空/未知 → auto（不参与区分）。"""
    d = (distro or "").strip().lower()
    return d if d in ("ubuntu", "centos") else "auto"


def _group_tuple(
    atype: str, run_target: str, install_path: str, host: str, distro: str = "auto"
) -> tuple[str, str, str, str, str]:
    """Instance identity: type + runtime + install + host + distro. Port is role-level, not instance."""
    return (
        (atype or "").strip(),
        (run_target or "windows").strip() or "windows",
        _norm_path(install_path),
        _norm_host(host),
        _norm_distro(distro),
    )


def _instances_fragmented_by_port(instances: dict[str, Any]) -> bool:
    """True when same framework install (type+run_target+install+host+distro) split into multiple instances."""
    buckets: dict[tuple[str, str, str, str, str], list[str]] = {}
    for iid, inst in instances.items():
        if not isinstance(inst, dict):
            continue
        atype = (inst.get("type") or "").strip()
        if not atype or atype == "none":
            continue
        key = _group_tuple(
            atype,
            (inst.get("run_target") or "windows").strip() or "windows",
            (inst.get("install_path") or "").strip(),
            (inst.get("host") or "").strip(),
            inst.get("distro") or "auto",
        )
        buckets.setdefault(key, []).append(iid)
    return any(len(ids) > 1 for ids in buckets.values())


def _roles_split_across_instances(agents: dict[str, Any], instances: dict[str, Any]) -> bool:
    """True when roles are orphaned (missing/invalid instance_id) → need re-attach."""
    for aid, rec in agents.items():
        if not isinstance(rec, dict):
            continue
        atype = (rec.get("type") or "none").strip() or "none"
        if atype == "none":
            continue
        iid = str(rec.get("instance_id") or "").strip()
        if not iid or iid not in instances:
            return True
    return False


def synthesize_instances_from_agents(cfg: dict[str, Any]) -> dict[str, Any]:
    """Idempotent: keep instances as SoT, merge fragmented instances, attach roles.

    - 运行环境字段 SoT 在实例；新数据角色仅凭 ``instance_id`` 归属。
    - 旧数据（角色携带 run_target/install_path/host）仍可反推/建实例（迁移兼容）。
    - 同 group（type+run_target+install_path+host+distro）多实例 → 合并（按 port 碎片修复）。
    """
    out = dict(cfg)
    agents = dict(out.get("agents") or {})
    instances = {
        iid: dict(inst)
        for iid, inst in (out.get("agent_instances") or {}).items()
        if isinstance(inst, dict)
    }

    for iid, inst in instances.items():
        inst.setdefault("enabled", True)
        inst.setdefault("distro", "auto")
        inst.setdefault("role_ids", [])
        inst.setdefault("label", f"{inst.get('type')}@{inst.get('run_target')}")

    # 1) 碎片合并：同 group 多实例 → 保留第一个，合并 role_ids
    merged_by_group: dict[tuple[str, str, str, str, str], str] = {}
    for iid, inst in list(instances.items()):
        atype = (inst.get("type") or "").strip()
        if not atype or atype == "none":
            continue
        key = _group_tuple(
            atype,
            (inst.get("run_target") or "windows").strip() or "windows",
            (inst.get("install_path") or "").strip(),
            (inst.get("host") or "").strip(),
            inst.get("distro") or "auto",
        )
        if key in merged_by_group:
            keep_iid = merged_by_group[key]
            keep = instances[keep_iid]
            for rid in (inst.get("role_ids") or []):
                if rid not in keep.setdefault("role_ids", []):
                    keep["role_ids"].append(rid)
            instances.pop(iid, None)
        else:
            merged_by_group[key] = iid

    # 2) 重建 role_ids（以角色归属为准）
    for iid in instances:
        instances[iid]["role_ids"] = []

    by_group: dict[tuple[str, str, str, str, str], str] = {}
    for iid, inst in instances.items():
        atype = (inst.get("type") or "").strip()
        if atype and atype != "none":
            key = _group_tuple(
                atype,
                (inst.get("run_target") or "windows").strip() or "windows",
                (inst.get("install_path") or "").strip(),
                (inst.get("host") or "").strip(),
                inst.get("distro") or "auto",
            )
            by_group.setdefault(key, iid)
    by_type: dict[str, str] = {}
    for iid, inst in instances.items():
        by_type.setdefault((inst.get("type") or "").strip(), iid)

    # 3) 角色归属
    for aid, rec in agents.items():
        if not isinstance(rec, dict):
            continue
        atype = (rec.get("type") or "none").strip() or "none"
        if atype == "none":
            continue
        iid = str(rec.get("instance_id") or "").strip()
        if not iid or iid not in instances:
            rec_run = (rec.get("run_target") or "").strip()
            rec_install = (rec.get("install_path") or "").strip()
            rec_host = str(rec.get("host") or "").strip()
            rec_distro = rec.get("distro") or "auto"
            if rec_run or rec_install or rec_host:
                # 旧数据迁移：角色携带运行环境字段 → 按 group 找/建实例
                key = _group_tuple(atype, rec_run or "windows", rec_install, rec_host, rec_distro)
                if key in by_group:
                    iid = by_group[key]
                else:
                    iid = _instance_key(
                        atype, rec_run or "windows", _norm_path(rec_install),
                        _norm_host(rec_host), None, _norm_distro(rec_distro),
                    )
                    by_group[key] = iid
                    instances[iid] = {
                        "id": iid,
                        "type": atype,
                        "run_target": rec_run or "windows",
                        "install_path": rec_install,
                        "host": _norm_host(rec_host),
                        "distro": _norm_distro(rec_distro),
                        "enabled": True,
                        "custom_paths": bool(rec.get("custom_paths")),
                        "paths": rec.get("paths") if isinstance(rec.get("paths"), dict) else {},
                        "role_ids": [],
                        "label": f"{atype}@{rec_run or 'windows'}",
                    }
            else:
                # 新数据：按 type 兜底归属
                iid = by_type.get(atype, "")
                if not iid:
                    continue  # 无实例可归属：不造实例（运行环境需显式创建）
        inst = instances[iid]
        rec = dict(rec)
        rec["instance_id"] = iid
        agents[aid] = rec
        if aid not in inst.setdefault("role_ids", []):
            inst["role_ids"].append(aid)

    out["agent_instances"] = instances
    out["agents"] = agents
    return out
