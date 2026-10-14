"""Claude Code 推送构建 — push 命令/argv 直启规格与模型 flag 解析。"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Optional

from lib.domain.errors import Fatal
from lib.infra.clock import now_dt, now_ts, now_utc_dt
from lib.infra.constants import PROJECT_ROOT_STR
from lib.infra.utils import json_read, json_write, to_wsl_path
from lib.infra.utils import no_window_creationflags
from lib.adapters.frameworks.claude_env import (
    ROOT, _bash_single_quote, _default_data_dir, _ps_escape, _wsl_exe, platform_settings, resolve_claude_bin, resolve_claude_home, resolve_project_dir,
)
from lib.adapters.frameworks import claude_env


def _flag_quote_value(value: str) -> str:
    """Quote CLI flag values with single quotes (safe inside PowerShell -Command)."""
    text = str(value)
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    return "'" + text.replace("'", "''") + "'"


def _interactive_claude_flags(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
) -> str:
    """浏览器/CLI 交互模式参数（无 -p）。"""
    claude_cfg = agent_cfg.get("claude") or {}
    permission = (claude_cfg.get("interactive_permission_mode") or "").strip()
    if not permission:
        permission = (claude_cfg.get("permission_mode") or "").strip()
    if not permission:
        permission = "acceptEdits"
    display = (agent_cfg.get("name") or agent_name).strip()
    parts = [
        f"--permission-mode {permission}",
        f"--name {_flag_quote_value(display)}",
    ]
    hint = (claude_cfg.get("interactive_system_prompt") or "").strip()
    if hint:
        parts.append(f"--append-system-prompt {_flag_quote_value(hint)}")
    mflag = _model_flag(agent_cfg, agent_types, None)
    if mflag:
        parts.append(mflag)
    extra = (claude_cfg.get("interactive_flags") or "").strip()
    if extra:
        parts.append(extra)
    else:
        allowed_tools = (claude_cfg.get("interactive_allowed_tools") or "").strip()
        if allowed_tools:
            parts.append(f"--allowedTools {_flag_quote_value(allowed_tools)}")
    return " ".join(parts)


def _model_flag(agent_cfg: dict, agent_types: dict, model_alias: Optional[str]) -> str:
    from lib.adapters.frameworks import model_flag, _flag_value

    if agent_cfg.get("model"):
        return f"--model {agent_cfg['model']}"
    raw = model_flag(agent_cfg, agent_types, "claude_code", model_alias)
    mid = _flag_value(raw, "--model ", "-m ")
    return f"--model {mid}" if mid else ""


def _claude_push_flags(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    model_alias: Optional[str],
) -> str:
    claude_cfg = agent_cfg.get("claude") or {}
    permission = (claude_cfg.get("permission_mode") or "").strip()
    if not permission:
        permission = "acceptEdits"

    parts = [
        "-p",
        "'MSG'",
        f"--permission-mode {permission}",
        "--output-format json",
    ]
    mflag = _model_flag(agent_cfg, agent_types, model_alias)
    if mflag:
        parts.append(mflag)
    max_turns = agent_cfg.get("max_turns")
    if max_turns is not None:
        parts.append(f"--max-turns {int(max_turns)}")
    extra = claude_cfg.get("push_flags") or ""
    if extra.strip():
        parts.append(extra.strip())
    elif permission == "dontAsk":
        default_tools = (claude_cfg.get("push_allowed_tools") or "").strip()
        if not default_tools:
            default_tools = "Bash,Read,Glob,Grep"
        parts.append(f'--allowedTools "{default_tools}"')
    return " ".join(parts)


def _build_windows_push(claude_bin: str, project_dir: str, flags: str, claude_home: str) -> str:
    ps_exe = claude_env._powershell_exe()
    if not ps_exe:
        raise Fatal(
            "PowerShell unavailable, cannot bridge Windows Claude Code",
            code="powershell_unavailable",
            zh="PowerShell 不可用，无法桥接 Windows Claude Code",
        )
    inner = (
        f"$env:USERPROFILE = Split-Path -Parent '{_ps_escape(claude_home)}'; "
        f"Set-Location '{_ps_escape(project_dir)}'; "
        f"& {claude_bin} {flags}"
    )
    if sys.platform == "win32":
        return f'"{ps_exe}" -NoProfile -Command "{inner}"'
    return f"{_bash_single_quote(ps_exe)} -NoProfile -Command {_bash_single_quote(inner)}"


def _build_linux_push(claude_bin: str, project_dir: str, flags: str, claude_home: str) -> str:
    env_prefix = f"CLAUDE_CONFIG_DIR={shlex.quote(claude_home)} "
    inner = f"cd {shlex.quote(project_dir)} && {env_prefix}{shlex.quote(claude_bin)} {flags}"
    if claude_env._runtime_os() == "windows":
        wsl = _wsl_exe()
        if not wsl:
            raise Fatal(
                "wsl.exe unavailable, cannot bridge Linux Claude Code",
                code="wsl_unavailable",
                zh="wsl.exe 不可用，无法桥接 Linux Claude Code",
            )
        return f"{shlex.quote(wsl)} -e bash -lc {_bash_single_quote(inner)}"
    return f"bash -lc {_bash_single_quote(inner)}"


def parse_model_name_from_push_template(cmd_template: str) -> str | None:
    """从 push CLI 模板提取 --model / -m 值。"""
    text = (cmd_template or "").strip()
    if not text:
        return None
    for pat in (
        r"--model\s+([^\s'\"]+)",
        r"-m\s+([^\s'\"]+)",
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return None


def _claude_push_argv_parts(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    model_alias: Optional[str],
    prompt: str,
    global_cfg: Optional[dict] = None,
) -> list[str]:
    """构建 claude -p 的 argv 片段（不含可执行文件路径）。"""
    claude_cfg = agent_cfg.get("claude") or {}
    permission = (claude_cfg.get("permission_mode") or "").strip()
    if not permission:
        permission = "acceptEdits"

    parts: list[str] = [
        "-p",
        prompt,
        "--permission-mode",
        permission,
        "--output-format",
        "json",
    ]
    mflag = _model_flag(agent_cfg, agent_types, model_alias)
    if mflag:
        mid = mflag.replace("--model ", "", 1).strip()
        if mid:
            parts.extend(["--model", mid])
    max_turns = agent_cfg.get("max_turns")
    if max_turns is not None:
        parts.extend(["--max-turns", str(int(max_turns))])
    # push_flags / push_allowed_tools 回落链：agent.claude 段 > 全局 mailbus_claude 段
    # （global_cfg 由调用方注入，函数保持纯函数——测试不读真实 store）
    gcfg = global_cfg or {}
    extra = (claude_cfg.get("push_flags") or gcfg.get("push_flags") or "").strip()
    if extra:
        parts.extend(shlex.split(extra, posix=False))
    elif permission == "dontAsk":
        default_tools = (
            claude_cfg.get("push_allowed_tools")
            or gcfg.get("push_allowed_tools")
            or ""
        ).strip()
        if not default_tools:
            default_tools = "Bash,Read,Glob,Grep"
        parts.extend(["--allowedTools", default_tools])
    return parts


def try_build_push_direct(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    data_dir: str | None = None,
    prompt: str = "",
    model_name: str | None = None,
    pipeline: bool = False,
) -> dict | None:
    """Claude Code 直连 argv（委托 lib.adapters.frameworks.direct_push，保留兼容导入）。"""
    from lib.adapters.frameworks.direct_push import try_build_push_direct as _push_direct

    return _push_direct(
        agent_name,
        agent_cfg,
        agent_types,
        data_dir=data_dir or _default_data_dir(),
        prompt=prompt,
        model_name=model_name,
        pipeline=pipeline,
    )


def build_push_command(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    model_alias: Optional[str] = None,
    *,
    data_dir: str | None = None,
) -> str:
    dd = data_dir or _default_data_dir()
    sync_py = os.path.join(ROOT, "tools", "sync-claude-agent-context.py")
    if os.path.isfile(sync_py):
        try:
            from lib.infra.utils import no_window_creationflags

            subprocess.run(
                [sys.executable, sync_py, agent_name, "--data-dir", dd],
                capture_output=True,
                timeout=45,
                check=False,
                creationflags=no_window_creationflags(),
            )
        except (subprocess.TimeoutExpired, OSError):
            pass
    global_cfg = claude_env.load_mailbus_claude(data_dir)
    plat = claude_env.resolve_claude_platform(global_cfg)
    if not claude_env._platform_enabled(global_cfg, plat):
        alt = "linux" if plat == "windows" else "windows"
        if claude_env._platform_enabled(global_cfg, alt):
            plat = alt
    plat_cfg = platform_settings(global_cfg, plat)
    claude_bin = resolve_claude_bin(plat_cfg)
    claude_home = resolve_claude_home(plat_cfg)
    project_dir = resolve_project_dir(agent_cfg, plat_cfg, agent_name)
    flags = _claude_push_flags(agent_name, agent_cfg, agent_types, model_alias)
    if plat == "windows":
        if not claude_env._powershell_exe():
            # 无 PowerShell 的环境（mailbus serve 容器等）：windows 桥是宿主专属。
            # 必须返回 None 让 scan 跳过该 agent、消息留队列待宿主 scan——
            # raise Fatal 会炸死整个 scan 推送队列（2026-09-21 停摆事故根因）。
            print(
                f"   ⚠ {agent_name}: claude windows-bridge is host-only, "
                "skipped (await host scan)"
            )
            return None
        return _build_windows_push(claude_bin, project_dir, flags, claude_home)
    return _build_linux_push(claude_bin, project_dir, flags, claude_home)
