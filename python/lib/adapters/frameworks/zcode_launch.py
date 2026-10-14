"""ZCode CLI（桌面应用自带运行时）宿主推送 — 镜像 claude_launch 的极简版。

二进制：`node <app>/resources/glm/zcode.cjs`，PATH shim `zcode.cmd` 可选。
隔离：ZCODE_HOME per-agent（实测 OAuth 认证跟随，不随 HOME 丢失）。
模式：`-p '<msg>' --mode yolo --cwd <dir>` 无头单发；GLM 为内置后端，无 model flag。
"""
from __future__ import annotations

import os
import re
import shutil

_BUNDLE_CANDIDATES = (
    r"D:\Zcode\resources\glm\zcode.cjs",
    r"C:\Zcode\resources\glm\zcode.cjs",
)

# 允许的无头权限模式（bus 派工为无人值守，默认 yolo 与 zcode -p 自身默认一致）
_ALLOWED_MODES = frozenset({"build", "edit", "plan", "yolo"})
_DEFAULT_MODE = "yolo"


def load_mailbus_zcode(data_dir: str) -> dict:
    """读 store/config.json 的 mailbus_zcode 段（可选）。"""
    if not data_dir:
        return {}
    from lib.infra.utils import json_read

    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    section = (cfg.get("mailbus_zcode") or {})
    return section if isinstance(section, dict) else {}


def _plat_cfg(global_cfg: dict) -> dict:
    """平台段：mailbus_zcode.windows（mailbus 只在宿主 Windows 推 zcode）。"""
    plat = global_cfg.get("windows")
    return plat if isinstance(plat, dict) else {}


def resolve_zcode_home(agent_name: str, data_dir: str = "") -> str:
    """per-agent 配置根：mailbus_zcode.windows.homes[agent] → ~/.zcode-<agent>。

    实证（2026-10-03）：ZCODE_HOME 指向新目录时 OAuth 认证跟随可用，
    会话/记忆按 agent 隔离，与桌面 app 的 ~/.zcode 互不干扰。
    """
    cfg = load_mailbus_zcode(data_dir)
    homes = (_plat_cfg(cfg).get("homes") or {})
    if agent_name and isinstance(homes, dict) and homes.get(agent_name):
        return os.path.normpath(str(homes[agent_name]))
    return os.path.normpath(os.path.expanduser(f"~/.zcode-{agent_name or 'default'}"))


def resolve_zcode_workdir(agent_cfg: dict) -> str:
    """推送工作目录：push.cwd / cwd（占位模板由 _push_cwd 处理过的实际路径）。"""
    push = agent_cfg.get("push") or {}
    cwd = push.get("cwd") or agent_cfg.get("cwd") or ""
    return os.path.normpath(cwd) if cwd else os.getcwd()


def resolve_zcode_cli(agent_cfg: dict | None = None, data_dir: str = "") -> list[str] | None:
    """zcode 启动 argv 前缀：[node, zcode.cjs] 优先，PATH shim `zcode` 兜底。

    返回 None = 本机无 zcode 可执行（调用方回 None → 消息留 pending 待宿主 scan）。
    """
    cfg = load_mailbus_zcode(data_dir)
    plat = _plat_cfg(cfg)
    cjs = str(plat.get("zcode_cjs") or "").strip()
    node = str(plat.get("node") or "").strip()
    if cjs and os.path.isfile(cjs):
        if node and os.path.isfile(node):
            return [node, cjs]
        node_exe = shutil.which("node")
        if node_exe:
            return [node_exe, cjs]
    for cand in _BUNDLE_CANDIDATES:
        if os.path.isfile(cand):
            node_exe = node or shutil.which("node")
            if node_exe:
                return [node_exe, cand]
    if shutil.which("zcode") or shutil.which("zcode.cmd"):
        return ["zcode"]
    return None


def _zcode_mode(agent_cfg: dict) -> str:
    zc = agent_cfg.get("zcode") or {}
    mode = str((zc.get("mode") if isinstance(zc, dict) else "") or _DEFAULT_MODE).strip()
    return mode if mode in _ALLOWED_MODES else _DEFAULT_MODE


def build_push_argv(
    agent_name: str,
    agent_cfg: dict,
    *,
    data_dir: str = "",
    prompt: str = "",
) -> dict | None:
    """direct_push 规格：{"argv", "env", "cwd"}；本机无 zcode 时 None。"""
    cli = resolve_zcode_cli(agent_cfg, data_dir)
    if not cli:
        return None
    home = resolve_zcode_home(agent_name, data_dir)
    workdir = resolve_zcode_workdir(agent_cfg)
    # zcode 不会自建 ZCODE_HOME（缺失即秒退）——spawn 前落盘，同 claude push 前写 settings 模式
    try:
        os.makedirs(home, exist_ok=True)
        os.makedirs(workdir, exist_ok=True)
    except OSError:
        pass
    mode = _zcode_mode(agent_cfg)
    argv = cli + ["-p", prompt, "--mode", mode, "--cwd", workdir]
    return {
        "argv": argv,
        "env": {"ZCODE_HOME": home},
        "cwd": workdir,
    }


def build_push_command(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    model_alias=None,
    *,
    data_dir: str = "",
) -> str:
    """shell 模板回退（pusher 在 direct 失败时才用；POSIX/bash 形态）。"""
    cli = resolve_zcode_cli(agent_cfg, data_dir)
    if not cli:
        return ""
    home = resolve_zcode_home(agent_name, data_dir)
    workdir = resolve_zcode_workdir(agent_cfg)
    mode = _zcode_mode(agent_cfg)
    quoted = " ".join(f"'{part}'" if " " in part else part for part in cli)
    return (
        f"cd '{workdir}' && ZCODE_HOME='{home}' {quoted} "
        f"-p 'MSG' --mode {mode} --cwd '{workdir}'"
    )


def build_interactive_command(agent_name: str, agent_cfg: dict, data_dir: str = "") -> str:
    """人工 TTY 窗口：全屏 TUI（共享 per-agent ZCODE_HOME）。"""
    cli = resolve_zcode_cli(agent_cfg, data_dir)
    if not cli:
        return ""
    home = resolve_zcode_home(agent_name, data_dir)
    quoted = " ".join(f"'{part}'" if " " in part else part for part in cli)
    return f"ZCODE_HOME='{home}' {quoted}"


def host_cli_active(ps_output: str) -> bool:
    """进程表里有无 zcode headless 推送（node ... zcode.cjs -p / zcode -p）。"""
    noise = ("grep", "get-ciminstance", "powershell -noprofile")
    token = re.compile(r"zcode(\.cjs|\.cmd)?[\"']?\s", re.IGNORECASE)
    flag = re.compile(r"\s-p\b|--prompt\b")
    for line in ps_output.splitlines():
        low = line.lower()
        if any(n in low for n in noise):
            continue
        if not token.search(line):
            continue
        if flag.search(line):
            return True
    return False
