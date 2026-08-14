"""Framework / role enable lifecycle — soft disable; plane saga F0–F6 / D0–D6."""
from __future__ import annotations

import os
import time
from typing import Any, Callable

from lib.composition import build_planes
from lib.domain.errors import Fatal
from lib.domain.health import probe_http
from lib.interfaces.plane import ContainerPlanePort, HostPlanePort
from lib.infra.utils import json_read, json_write, named_lock

LogFn = Callable[[str], None]


def _log(log: LogFn | None, msg: str) -> None:
    if log:
        log(msg)


def list_active_agents(cfg: dict) -> dict[str, dict]:
    """Agents that are enabled at role level and whose framework is enabled.

    三级门禁：角色 enabled（退役/工作）→ 实例 enabled（容器是否监测）→ 框架 registry enabled。
    """
    frameworks = cfg.get("frameworks") or {}
    instances = cfg.get("agent_instances") or {}
    agents = cfg.get("agents") or {}
    out = {}
    for aid, ac in agents.items():
        if not isinstance(ac, dict):
            continue
        if ac.get("enabled") is False:
            continue
        # 实例级监测开关：disabled → 该实例下所有角色下架（不参与派发/监测，但不删除角色记录）
        iid = str(ac.get("instance_id") or "").strip()
        if iid:
            inst = instances.get(iid)
            if isinstance(inst, dict) and inst.get("enabled") is False:
                continue
        fw = str(ac.get("type") or ac.get("framework") or "")
        fw_cfg = frameworks.get(fw) or frameworks.get(fw.replace("_", "-")) or {}
        # If frameworks section missing entry, treat as enabled for backward compat when agent.enabled True
        if fw and fw_cfg.get("enabled") is False:
            continue
        if ac.get("enabled") is True or (ac.get("enabled") is None and fw_cfg.get("enabled") is True):
            out[aid] = ac
        elif ac.get("enabled") is None and not frameworks:
            # legacy: no frameworks gate
            out[aid] = ac
    return out


def running_tasks_for_agents(data_dir: str, agent_ids: list[str]) -> list[dict]:
    """Scan lightweight task index for in-flight work."""
    hits = []
    tasks_dir = os.path.join(data_dir, "tasks")
    if not os.path.isdir(tasks_dir):
        # also check iterations / queue markers
        return hits
    for root, _dirs, files in os.walk(tasks_dir):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            path = os.path.join(root, fn)
            try:
                data = json_read(path, {})
            except Exception:
                continue
            st = str(data.get("status") or data.get("state") or "").lower()
            if st not in ("processing", "running", "in_progress", "pushed", "acknowledged"):
                continue
            agent = data.get("agent") or data.get("agent_id") or data.get("assignee")
            if agent in agent_ids:
                hits.append({"path": path, "agent": agent, "status": st, "id": data.get("id") or fn})
    return hits


def fail_tasks(task_hits: list[dict], reason: str = "framework_or_role_disabled") -> int:
    n = 0
    for hit in task_hits:
        path = hit.get("path")
        if not path or not os.path.isfile(path):
            continue
        data = json_read(path, {})
        data["status"] = "failed"
        data["error"] = reason
        json_write(path, data)
        n += 1
    return n


def _lifecycle_lock_name(key: str) -> str:
    """Windows-safe lock file name (no colon)."""
    return key.replace(":", "__").replace("/", "_")


def _normalize_argv(cmd: Any) -> list[str] | None:
    if not cmd:
        return None
    if isinstance(cmd, list):
        out = [str(x) for x in cmd if str(x)]
        return out or None
    return None


def _plane_for(mount_mode: str, host: HostPlanePort, container: ContainerPlanePort):
    return container if mount_mode == "container" else host


def enable_framework(
    data_dir: str,
    framework_id: str,
    *,
    mount_mode: str = "container",
    root_path: str = "",
    start_cmd: list[str] | None = None,
    stop_cmd: list[str] | None = None,
    health_url: str = "",
    log: LogFn | None = None,
) -> dict[str, Any]:
    """Enable framework with lifecycle lock (saga F0–F6)."""
    with named_lock(_lifecycle_lock_name(f"lifecycle:fw:{framework_id}"), blocking=True, timeout=30.0) as acquired:
        if not acquired:
            return {"ok": False, "error": "lock_busy", "error_code": "lock_busy"}
        return _enable_framework_locked(
            data_dir,
            framework_id,
            mount_mode=mount_mode,
            root_path=root_path,
            start_cmd=start_cmd,
            stop_cmd=stop_cmd,
            health_url=health_url,
            log=log,
        )


def _enable_framework_locked(
    data_dir: str,
    framework_id: str,
    *,
    mount_mode: str = "container",
    root_path: str = "",
    start_cmd: list[str] | None = None,
    stop_cmd: list[str] | None = None,
    health_url: str = "",
    log: LogFn | None = None,
) -> dict[str, Any]:
    cfg_path = os.path.join(data_dir, "config.json")
    cfg = json_read(cfg_path, {})
    frameworks = cfg.setdefault("frameworks", {})
    entry = frameworks.setdefault(framework_id, {})
    snap = dict(entry)

    # F0
    if mount_mode not in ("container", "host"):
        return {"ok": False, "error": "mount_mode must be container|host (mutex)", "error_code": "fatal"}
    planes = build_planes(data_dir, frameworks)
    try:
        planes.mutex.assert_exclusive(framework_id, mount_mode)
    except Fatal as exc:
        return {"ok": False, "error": exc.message, "error_code": exc.code}

    # F1–F2: intent
    entry["mount_mode"] = mount_mode
    if root_path:
        entry["root_path"] = root_path
    argv_start = _normalize_argv(start_cmd)
    argv_stop = _normalize_argv(stop_cmd)
    if argv_start:
        entry["start_cmd"] = argv_start
    if argv_stop:
        entry["stop_cmd"] = argv_stop
    if health_url:
        entry["health_url"] = health_url
    entry["enabled"] = True
    entry["pending_enable"] = True
    json_write(cfg_path, cfg)

    plane = _plane_for(mount_mode, planes.host, planes.container)

    def _compensate(err: str) -> dict[str, Any]:
        try:
            plane.stop_framework(framework_id)
        except Exception as stop_exc:
            _log(log, f"compensate stop: {stop_exc}")
        frameworks[framework_id] = snap
        json_write(cfg_path, cfg)
        return {
            "ok": False,
            "compensated": True,
            "error": err,
            "error_code": "retryable",
        }

    # F3
    _log(log, f"enable {framework_id} plane={mount_mode} start")
    try:
        started = plane.start_framework(framework_id)
    except Exception as exc:
        return _compensate(str(exc))
    if not started.ok:
        return _compensate(started.detail or "plane_start_failed")

    # F4 probe×3 (extra to start's internal probe)
    last_probe = ""
    for attempt in range(1, 4):
        _log(log, f"enable {framework_id} probe {attempt}/3")
        try:
            pr = plane.probe_framework(framework_id)
        except Exception as exc:
            last_probe = str(exc)
            time.sleep(1)
            continue
        if pr.ok:
            break
        last_probe = pr.detail or "probe_failed"
        time.sleep(1)
    else:
        return _compensate(last_probe or "probe failed after 3 retries")

    # F5 commit
    entry.pop("pending_enable", None)
    entry["enabled"] = True
    json_write(cfg_path, cfg)
    return {"ok": True, "framework": entry}


def disable_framework(
    data_dir: str,
    framework_id: str,
    *,
    confirm_fail_tasks: bool = False,
    stop_cmd: list[str] | None = None,
    log: LogFn | None = None,
) -> dict[str, Any]:
    with named_lock(_lifecycle_lock_name(f"lifecycle:fw:{framework_id}"), blocking=True, timeout=30.0) as acquired:
        if not acquired:
            return {"ok": False, "error": "lock_busy", "error_code": "lock_busy"}
        return _disable_framework_locked(
            data_dir,
            framework_id,
            confirm_fail_tasks=confirm_fail_tasks,
            stop_cmd=stop_cmd,
            log=log,
        )


def _disable_framework_locked(
    data_dir: str,
    framework_id: str,
    *,
    confirm_fail_tasks: bool = False,
    stop_cmd: list[str] | None = None,
    log: LogFn | None = None,
) -> dict[str, Any]:
    cfg_path = os.path.join(data_dir, "config.json")
    cfg = json_read(cfg_path, {})
    agents = cfg.get("agents") or {}
    affected = [
        aid for aid, ac in agents.items()
        if isinstance(ac, dict) and (ac.get("type") or ac.get("framework")) == framework_id
    ]
    running = running_tasks_for_agents(data_dir, affected)
    if running and not confirm_fail_tasks:
        return {
            "ok": False,
            "needs_confirm": True,
            "running_tasks": running,
            "message": "Tasks still running; confirm to fail them and disable",
            "error_code": "needs_human",
        }
    if running and confirm_fail_tasks:
        fail_tasks(running)

    fw = cfg.setdefault("frameworks", {}).setdefault(framework_id, {})
    mount_mode = str(fw.get("mount_mode") or "container")
    argv_stop = _normalize_argv(stop_cmd)
    if argv_stop:
        fw["stop_cmd"] = argv_stop
        json_write(cfg_path, cfg)

    # D4 — stop plane; failures logged, still disable
    planes = build_planes(data_dir, cfg.get("frameworks") or {})
    plane = _plane_for(mount_mode if mount_mode in ("container", "host") else "container", planes.host, planes.container)
    try:
        stopped = plane.stop_framework(framework_id)
        if not stopped.ok:
            _log(log, f"stop_framework: {stopped.detail}")
    except Exception as exc:
        _log(log, f"stop_framework error: {exc}")

    fw["enabled"] = False
    fw.pop("pending_enable", None)
    json_write(cfg_path, cfg)
    return {"ok": True, "disabled": framework_id, "failed_tasks": len(running)}


def set_role_enabled(data_dir: str, agent_id: str, enabled: bool) -> dict[str, Any]:
    with named_lock(_lifecycle_lock_name(f"lifecycle:role:{agent_id}"), blocking=True, timeout=30.0) as acquired:
        if not acquired:
            return {"ok": False, "error": "lock_busy", "error_code": "lock_busy"}
        return _set_role_enabled_locked(data_dir, agent_id, enabled)


def _set_role_enabled_locked(data_dir: str, agent_id: str, enabled: bool) -> dict[str, Any]:
    cfg_path = os.path.join(data_dir, "config.json")
    cfg = json_read(cfg_path, {})
    agents = cfg.get("agents") or {}
    if agent_id not in agents:
        return {"ok": False, "error": f"unknown agent {agent_id}", "error_code": "fatal"}
    snap = dict(agents[agent_id]) if isinstance(agents[agent_id], dict) else {}
    agents[agent_id]["enabled"] = bool(enabled)
    try:
        from lib.composition import get_integrations

        if enabled:
            get_integrations().write_mcp_mount_hint(data_dir, agent_id)
        else:
            get_integrations().clear_mcp_mount_hint(data_dir, agent_id)
            get_integrations().archive_agentmemory(data_dir, agent_id)
    except Exception:
        agents[agent_id] = snap
        json_write(cfg_path, cfg)
        return {"ok": False, "compensated": True, "error": "agentmemory_mount_failed", "error_code": "retryable"}
    json_write(cfg_path, cfg)
    return {"ok": True, "agent_id": agent_id, "enabled": enabled}


# re-export for callers that used lifecycle.probe_http
__all__ = [
    "disable_framework",
    "enable_framework",
    "fail_tasks",
    "list_active_agents",
    "probe_http",
    "running_tasks_for_agents",
    "set_role_enabled",
]
