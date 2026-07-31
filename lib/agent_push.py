"""跨平台 agent 推送 — subprocess argv 直启（不经 shell / ps1 / bash -lc 字符串）。

mailbus scan/pusher 优先走 try_build_push_direct；失败时回退 adapter shell 模板。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Optional

from lib.adapters.frameworks import (
    ClineAdapter,
    CodexAdapter,
    HermesAdapter,
    HermesProfileAdapter,
    OpenClawAdapter,
    OpenCodeAdapter,
    _flag_value,
    _push_cwd,
    get_adapter,
    model_flag,
    resolve_container,
)
from .claude_launch import parse_model_name_from_push_template

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_model_from_push_template(cmd_template: str) -> str | None:
    """从 push CLI 模板提取 --model / -m 值（claude / codex 等通用）。"""
    return parse_model_name_from_push_template(cmd_template)


def _docker_bin() -> str:
    return shutil.which("docker") or shutil.which("docker.exe") or "docker"


def _claude_direct(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    data_dir: str,
    prompt: str,
    model_name: str | None,
) -> dict | None:
    from .claude_launch import (
        _claude_push_argv_parts,
        _platform_enabled,
        _sync_claude_agent_context,
        _to_fs_path,
        load_mailbus_claude,
        platform_settings,
        resolve_claude_executable,
        resolve_claude_home,
        resolve_claude_platform,
        resolve_project_dir,
    )

    dd = data_dir
    _sync_claude_agent_context(agent_name, dd)
    global_cfg = load_mailbus_claude(dd)
    plat = resolve_claude_platform(global_cfg)
    if not _platform_enabled(global_cfg, plat):
        alt = "linux" if plat == "windows" else "windows"
        if _platform_enabled(global_cfg, alt):
            plat = alt
        else:
            return None
    plat_cfg = platform_settings(global_cfg, plat)
    claude_exe = resolve_claude_executable(plat_cfg, plat)
    if not claude_exe:
        return None

    claude_home = resolve_claude_home(plat_cfg, agent_name)
    project_dir = resolve_project_dir(agent_cfg, plat_cfg, agent_name)
    model_alias = model_name
    if not model_alias:
        models = agent_cfg.get("models") or []
        model_alias = models[0] if models else None

    argv = [claude_exe] + _claude_push_argv_parts(
        agent_name, agent_cfg, agent_types, model_alias, prompt,
    )
    return {
        "argv": argv,
        "env": {"CLAUDE_CONFIG_DIR": _to_fs_path(claude_home)},
        "cwd": _to_fs_path(project_dir),
    }


def _codex_direct(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    prompt: str,
    model_name: str | None,
    pipeline: bool,
) -> dict | None:
    adapter = CodexAdapter()
    service = adapter._service(agent_name, agent_cfg)
    container = resolve_container(agent_cfg, agent_name, service)
    if not container:
        return None
    cwd = _push_cwd(agent_cfg)
    model = adapter._model_id(agent_cfg, agent_types, model_name, pipeline=pipeline)
    sandbox = adapter._codex_sandbox(agent_cfg, pipeline=pipeline)
    argv = [
        _docker_bin(), "exec", container,
        "codex", "exec",
        "--json", "--ephemeral", "--skip-git-repo-check",
        "--cd", cwd,
        "-s", sandbox,
        "-c", 'approval_policy="never"',
        "-m", model,
        prompt,
    ]
    return {"argv": argv, "env": {}, "cwd": None}


def _hermes_direct(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    prompt: str,
    model_name: str | None,
    profile: bool,
) -> dict | None:
    adapter = HermesProfileAdapter() if profile else HermesAdapter()
    container = resolve_container(agent_cfg, agent_name, adapter.container_service)
    if not container:
        return None
    mflag = model_flag(agent_cfg, agent_types, adapter.type_name, model_name)
    argv = [_docker_bin(), "exec", container, "hermes", "chat"]
    if profile:
        prof = adapter._profile(agent_name, agent_cfg)  # type: ignore[attr-defined]
        if prof:
            argv.extend(["--profile", prof])
    mid = _flag_value(mflag, "--model ", "-m ")
    if mid:
        argv.extend(["--model", mid])
    argv.extend(["--yolo", "-q", prompt, "-Q"])
    return {"argv": argv, "env": {}, "cwd": None}


def _openclaw_direct(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    prompt: str,
    model_name: str | None,
) -> dict | None:
    adapter = OpenClawAdapter()
    container = resolve_container(agent_cfg, agent_name, adapter.container_service)
    if not container:
        return None
    agent_id = adapter._agent_id(agent_name, agent_cfg)
    state_dir = adapter._state_dir(agent_name, agent_cfg)
    mflag = model_flag(agent_cfg, agent_types, adapter.type_name, model_name)
    timeout = str(adapter.push_timeout_seconds(pipeline=True, agent_cfg=agent_cfg))
    argv = [
        _docker_bin(), "exec",
        "-e", f"OPENCLAW_STATE_DIR={state_dir}",
        container,
        "openclaw", "agent", "--local",
        "--agent", agent_id,
        "--message", prompt,
    ]
    mid = _flag_value(mflag, "--model ", "-m ")
    if mid:
        argv.extend(["--model", mid])
    argv.extend(["--timeout", timeout])
    return {"argv": argv, "env": {}, "cwd": None}


def _cline_direct(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    prompt: str,
    model_name: str | None,
) -> dict | None:
    adapter = ClineAdapter()
    container = resolve_container(agent_cfg, agent_name, adapter.container_service)
    if not container:
        return None
    cwd = _push_cwd(agent_cfg)
    provider = adapter._provider_id(agent_cfg, agent_types, model_name)
    model = adapter._model_id(agent_cfg, agent_types, model_name)
    timeout = str(adapter.push_timeout_seconds(pipeline=True, agent_cfg=agent_cfg))
    argv = [
        _docker_bin(), "exec", container,
        "cline", prompt,
        "-P", provider,
        "-m", model,
        "-t", timeout,
        "-c", cwd,
        "--auto-approve", "true",
    ]
    return {"argv": argv, "env": {}, "cwd": None}


def _opencode_direct(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    prompt: str,
    model_name: str | None,
) -> dict | None:
    adapter = OpenCodeAdapter()
    container = resolve_container(agent_cfg, agent_name, adapter.container_service)
    if not container:
        return None
    cwd = _push_cwd(agent_cfg)
    mflag = adapter._model_flag(agent_cfg, agent_types, model_name)
    argv = [
        _docker_bin(), "exec", container,
        "opencode", "run", prompt,
        "--dangerously-skip-permissions",
    ]
    mid = _flag_value(mflag, "--model ", "-m ")
    if mid:
        argv.extend(["--model", mid])
    argv.extend(["--dir", cwd])
    return {"argv": argv, "env": {}, "cwd": None}


def try_build_push_direct(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    data_dir: str,
    prompt: str = "",
    model_name: str | None = None,
    pipeline: bool = False,
) -> dict | None:
    """
    构建 subprocess.Popen(argv=...) 规格；成功返回 {"argv", "env", "cwd"}，不支持则 None。
    """
    atype = (agent_cfg.get("type") or "").strip()
    if not atype or not get_adapter(atype):
        return None

    built = None
    if atype == "claude_code":
        built = _claude_direct(
            agent_name, agent_cfg, agent_types,
            data_dir=data_dir, prompt=prompt, model_name=model_name,
        )
    elif atype == "codex":
        built = _codex_direct(
            agent_name, agent_cfg, agent_types,
            prompt=prompt, model_name=model_name, pipeline=pipeline,
        )
    elif atype == "hermes_profile":
        built = _hermes_direct(
            agent_name, agent_cfg, agent_types,
            prompt=prompt, model_name=model_name, profile=True,
        )
    elif atype == "hermes":
        built = _hermes_direct(
            agent_name, agent_cfg, agent_types,
            prompt=prompt, model_name=model_name, profile=False,
        )
    elif atype == "openclaw":
        built = _openclaw_direct(
            agent_name, agent_cfg, agent_types,
            prompt=prompt, model_name=model_name,
        )
    elif atype == "cline":
        built = _cline_direct(
            agent_name, agent_cfg, agent_types,
            prompt=prompt, model_name=model_name,
        )
    elif atype == "opencode":
        built = _opencode_direct(
            agent_name, agent_cfg, agent_types,
            prompt=prompt, model_name=model_name,
        )
    if not built or not built.get("argv"):
        return built
    from lib.adapters.frameworks.support import assert_spawn_argv_allowed
    from lib.utils import json_read

    cfg = json_read(os.path.join(data_dir, "config.json"), {}) if data_dir else {}
    assert_spawn_argv_allowed(list(built["argv"]), cfg)
    return built


def run_push_direct(spec: dict, *, wait: bool = True) -> int:
    """独立运维：执行 direct push 并可选等待。"""
    env = os.environ.copy()
    env.update(spec.get("env") or {})
    proc = subprocess.Popen(
        spec["argv"],
        cwd=spec.get("cwd") or None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    if not wait:
        return 0
    out, _ = proc.communicate()
    if out and isinstance(out, bytes):
        sys.stdout.buffer.write(out)
    elif out:
        sys.stdout.write(out)
    return proc.returncode or 0
