"""Claude Code 宿主环境 — 配置/平台判定、二进制发现、路径/home 解析与 shell 转义。"""
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


ROOT = PROJECT_ROOT_STR


PS_HELPER = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"


def _default_data_dir() -> str:
    from lib.infra.constants import MAILBUS_DATA_STR

    for cand in (
        os.environ.get("DATA_DIR"),
        os.environ.get("MAILBUS_DATA"),
        MAILBUS_DATA_STR,
        os.path.join(ROOT, "store"),
        "/mailbus/store",
    ):
        if cand and os.path.isfile(os.path.join(cand, "config.json")):
            return os.path.abspath(cand)
    return MAILBUS_DATA_STR if os.path.isdir(MAILBUS_DATA_STR) else os.path.join(ROOT, "store")


def _powershell_exe() -> str:
    if sys.platform == "win32":
        windir = os.environ.get("SystemRoot", r"C:\Windows")
        ps = os.path.join(windir, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        if os.path.isfile(ps):
            return ps
    if os.path.isfile(PS_HELPER):
        return PS_HELPER
    return ""


def _wsl_exe() -> str:
    return shutil.which("wsl.exe") or shutil.which("wsl") or ""


def _runtime_os() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    uname = platform.system().lower()
    if uname == "windows":
        return "windows"
    return "linux"


def load_mailbus_claude(data_dir: str | None = None) -> dict:
    dd = data_dir or _default_data_dir()
    cfg = json_read(os.path.join(os.path.abspath(dd), "config.json"), {})
    return cfg.get("mailbus_claude") or {}


def resolve_claude_platform(global_cfg: dict | None = None) -> str:
    global_cfg = global_cfg or {}
    configured = (global_cfg.get("platform") or "auto").strip().lower()
    if configured in ("windows", "linux"):
        return configured
    return _runtime_os()


def platform_settings(global_cfg: dict, plat: str) -> dict:
    block = global_cfg.get(plat) or {}
    return block if isinstance(block, dict) else {}


def _platform_enabled(global_cfg: dict, plat: str) -> bool:
    block = platform_settings(global_cfg, plat)
    return block.get("enabled", True) is not False


def resolve_claude_bin(plat_cfg: dict) -> str:
    return (plat_cfg.get("claude_bin") or "claude").strip() or "claude"


def _windows_ps_helper() -> str:
    if sys.platform == "win32":
        return _powershell_exe()
    return PS_HELPER if os.path.isfile(PS_HELPER) else ""


def _scan_claude_install_paths() -> list[str]:
    """扫描 Windows 侧常见 claude 安装位置（WSL 与原生 Windows 均可用）。"""
    found: list[str] = []
    profile_roots: list[str] = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        local = os.environ.get("LOCALAPPDATA", "")
        if appdata:
            profile_roots.append(appdata)
        if local:
            profile_roots.append(local)
        home = os.path.expanduser("~")
        if home:
            profile_roots.append(home)
    users_root = "/mnt/c/Users" if os.path.isdir("/mnt/c/Users") else ""
    if users_root:
        try:
            for user in os.listdir(users_root):
                base = os.path.join(users_root, user)
                if not os.path.isdir(base):
                    continue
                profile_roots.extend([
                    os.path.join(base, "AppData", "Roaming"),
                    os.path.join(base, "AppData", "Local"),
                ])
        except OSError:
            pass
    rel_paths = (
        os.path.join("npm", "claude.cmd"),
        os.path.join("npm", "claude"),
        os.path.join("npm", "claude.ps1"),
        os.path.join("Programs", "claude", "claude.exe"),
    )
    extra_candidates = (
        "/mnt/e/nodejs/node_global/claude.ps1",
        "/mnt/e/nodejs/node_global/claude.cmd",
        "/mnt/c/nodejs/node_global/claude.ps1",
        "/mnt/c/nodejs/node_global/claude.cmd",
    )
    seen: set[str] = set()
    for root in profile_roots:
        for rel in rel_paths:
            cand = os.path.join(root, rel)
            if cand in seen:
                continue
            seen.add(cand)
            if os.path.isfile(cand):
                found.append(cand)
    for cand in extra_candidates:
        if cand not in seen and os.path.isfile(cand):
            seen.add(cand)
            found.append(cand)
    return found


def _windows_path_exists(path: str) -> bool:
    norm = _normalize_windows_path(path)
    if len(norm) >= 2 and norm[1] == ":":
        if sys.platform == "win32":
            return os.path.isfile(norm.replace("/", os.sep))
        wsl_path = to_wsl_path(norm)
        return os.path.isfile(wsl_path)
    return os.path.isfile(norm)


def resolve_claude_executable(plat_cfg: dict, plat: str) -> str:
    """跨平台解析 claude 可执行文件（Windows .exe / Linux·macOS PATH）。"""
    if plat == "windows":
        return resolve_claude_native_exe(resolve_windows_claude_bin(plat_cfg))
    configured = resolve_claude_bin(plat_cfg)
    fs = _to_fs_path(configured)
    if fs and os.path.isfile(fs):
        return fs
    found = shutil.which(configured) or shutil.which("claude")
    return found or configured


def resolve_claude_native_exe(claude_bin: str) -> str:
    """npm 包装脚本 (.ps1/.cmd) → 原生 claude.exe，供 Python subprocess 直启。"""
    norm = _normalize_windows_path(claude_bin)
    fs_path = _to_fs_path(norm)
    if fs_path.lower().endswith(".exe") and os.path.isfile(fs_path):
        return fs_path
    base = os.path.dirname(fs_path)
    bundled = os.path.join(
        base, "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe",
    )
    if os.path.isfile(bundled):
        return bundled
    if os.path.isfile(fs_path):
        return fs_path
    return fs_path


def resolve_windows_claude_bin(plat_cfg: dict) -> str:
    """解析 Windows 上 claude 可执行文件的完整路径（WSL 调 PowerShell 时 PATH 不完整）。"""
    configured = resolve_claude_bin(plat_cfg)
    norm = _normalize_windows_path(configured)
    if len(norm) >= 2 and norm[1] == ":" and _windows_path_exists(norm):
        return norm

    ps = _windows_ps_helper()
    if ps:
        q = configured.replace("'", "''")
        script = (
            "$env:Path=[Environment]::GetEnvironmentVariable('Path','User')+';'"
            "+[Environment]::GetEnvironmentVariable('Path','Machine'); "
            f"$c=Get-Command '{q}' -ErrorAction SilentlyContinue; "
            "if($c -and $c.Source){Write-Output $c.Source}"
        )
        try:
            from lib.infra.utils import no_window_creationflags

            r = subprocess.run(
                [ps, "-NoProfile", "-Command", script],
                capture_output=True,
                timeout=15,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=no_window_creationflags(),
            )
            for line in (r.stdout or "").splitlines():
                path = _normalize_windows_path(line.strip())
                if path and _windows_path_exists(path):
                    return path
        except (subprocess.TimeoutExpired, OSError):
            pass

    for cand in _scan_claude_install_paths():
        return _normalize_windows_path(cand.replace("\\", "/"))
    return configured


def _powershell_path_prefix() -> str:
    """WSL 启动的 PowerShell 默认 PATH 不含 npm，需显式合并 User+Machine PATH。"""
    return (
        "$env:Path=[Environment]::GetEnvironmentVariable('Path','User')+';'"
        "+[Environment]::GetEnvironmentVariable('Path','Machine'); "
    )


def _agent_claude_home(base: str, agent_name: str) -> str:
    norm = _normalize_windows_path(base.rstrip("/"))
    if norm.endswith(".claude"):
        return f"{norm}-{agent_name}"
    parent = norm.rsplit("/", 1)[0] if len(norm) > 3 and "/" in norm[2:] else norm
    return f"{parent}/.claude-{agent_name}"


def resolve_claude_home(plat_cfg: dict, agent_name: str = "") -> str:
    """每个 agent 独立 CLAUDE_CONFIG_DIR，避免共用 ~/.claude。"""
    homes = plat_cfg.get("claude_homes") or {}
    if agent_name and isinstance(homes, dict) and homes.get(agent_name):
        return _normalize_windows_path(str(homes[agent_name]))
    base = (plat_cfg.get("claude_home") or "").strip()
    if base:
        norm = _normalize_windows_path(base)
        if agent_name:
            return _agent_claude_home(norm, agent_name)
        if len(norm) >= 2 and norm[1] == ":":
            return norm
        return os.path.abspath(norm.replace("/", os.sep))
    default = os.path.join(os.path.expanduser("~"), ".claude")
    if agent_name:
        return _agent_claude_home(_normalize_windows_path(default), agent_name)
    return os.path.abspath(default)


def _is_agent_claude_workspace(path: str, agent_name: str) -> bool:
    """push.cwd / workspace 已指向 agent 独立目录时勿再追加 .mailbus/claude/<agent>。"""
    if not path or not agent_name:
        return False
    norm = _normalize_windows_path(path).rstrip("/\\")
    suffix = f".mailbus/claude/{agent_name}"
    flat = norm.replace("\\", "/")
    return flat.endswith(suffix)


def resolve_claude_workspace(agent_cfg: dict, plat_cfg: dict, agent_name: str = "") -> str:
    """交互/同步用的项目目录（含独立 CLAUDE.md，默认同 push.cwd 下的 .mailbus/claude/<agent>）。"""
    roots = plat_cfg.get("claude_workspace_roots") or {}
    if agent_name and roots.get(agent_name):
        return _normalize_windows_path(str(roots[agent_name]))
    workspace = (agent_cfg.get("workspace") or "").strip()
    if agent_name and workspace and not workspace.startswith("/path/") and _is_agent_claude_workspace(workspace, agent_name):
        return _normalize_windows_path(workspace)
    base = resolve_project_dir(agent_cfg, plat_cfg, agent_name)
    if not agent_name:
        return base
    if _is_agent_claude_workspace(base, agent_name):
        return _normalize_windows_path(base.rstrip("/"))
    return _normalize_windows_path(f"{base.rstrip('/')}/.mailbus/claude/{agent_name}")


def _to_fs_path(path: str) -> str:
    """宿主机可访问路径：Windows 上 /mnt/e/... → E:\\...；Linux/WSL 上 C:/... → /mnt/c/...。"""
    norm = _normalize_windows_path(path)
    if sys.platform == "win32":
        if norm.startswith("/mnt/"):
            norm = _to_powershell_path(norm)
        return norm.replace("/", os.sep) if len(norm) >= 2 and norm[1] == ":" else norm
    if len(norm) >= 2 and norm[1] == ":":
        return to_wsl_path(norm)
    return norm


def _to_powershell_path(path: str) -> str:
    """PowerShell Set-Location 用 Windows 路径（/mnt/e/... → E:/...）。"""
    norm = _normalize_windows_path(path)
    m = re.match(r"^/mnt/([a-z])/(.*)$", norm, re.I)
    if m:
        return f"{m.group(1).upper()}:/{m.group(2)}"
    return norm


def _claude_settings_path(claude_home: str) -> str:
    home = _normalize_windows_path(claude_home)
    if len(home) >= 2 and home[1] == ":":
        return home.replace("/", os.sep) + os.sep + "settings.json"
    return os.path.join(home, "settings.json")


def _claude_settings_path_fs(claude_home: str) -> str:
    """settings.json 在本地文件系统上的可访问路径。"""
    target = _claude_settings_path(claude_home)
    parent = target.rsplit(os.sep, 1)[0] if os.sep in target else os.path.dirname(target)
    return os.path.join(_to_fs_path(parent), "settings.json")


def _read_settings_file(path: str) -> dict:
    """读取 Claude settings.json（兼容 UTF-8 BOM，不走 json_read 缓存）。"""
    if not os.path.isfile(path):
        return {}
    for enc in ("utf-8-sig", "utf-8"):
        try:
            with open(path, encoding=enc) as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError, ValueError):
            continue
    return {}


def ensure_claude_agent_settings(agent_name: str, data_dir: str) -> dict:
    """为 per-agent CLAUDE_CONFIG_DIR 写入 settings.json（继承主 ~/.claude 的 MiniMax 路由）。"""
    cfg = json_read(os.path.join(os.path.abspath(data_dir), "config.json"), {})
    agent_cfg = (cfg.get("agents") or {}).get(agent_name) or {}
    global_cfg = load_mailbus_claude(data_dir)
    plat, plat_cfg = resolve_claude_plat_cfg(global_cfg)
    if plat_cfg.get("ensure_on_launch", True) is False:
        return {"agent": agent_name, "skipped": True}

    agent_home = resolve_claude_home(plat_cfg, agent_name)
    base_home = resolve_claude_home(plat_cfg, "")
    target = _claude_settings_path_fs(agent_home)
    os.makedirs(os.path.dirname(target), exist_ok=True)

    settings: dict = {}
    base_settings = _claude_settings_path_fs(base_home)
    if os.path.isfile(base_settings):
        settings = _read_settings_file(base_settings)
    elif isinstance(plat_cfg.get("env"), dict):
        settings = {"env": dict(plat_cfg["env"])}

    env = dict(settings.get("env") or {})
    for src in (
        plat_cfg.get("env"),
        (plat_cfg.get("agent_env") or {}).get(agent_name) if isinstance(plat_cfg.get("agent_env"), dict) else None,
        (agent_cfg.get("claude") or {}).get("env"),
    ):
        if isinstance(src, dict):
            env.update(src)
    if env:
        settings["env"] = env

    json_write(target, settings)
    return {
        "agent": agent_name,
        "claude_home": agent_home,
        "settings": target,
        "has_base_url": bool(env.get("ANTHROPIC_BASE_URL")),
    }


def _powershell_env_from_settings(agent_name: str, data_dir: str) -> str:
    """将 settings.json env 注入 PowerShell（WSL 桥接时 Claude 仍读 CLAUDE_CONFIG_DIR）。"""
    info = ensure_claude_agent_settings(agent_name, data_dir)
    settings = _read_settings_file(info["settings"])
    env = settings.get("env") or {}
    parts: list[str] = []
    for key in (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "API_TIMEOUT_MS",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    ):
        val = env.get(key)
        if val is not None and str(val).strip():
            parts.append(f"$env:{key}='{_ps_escape(str(val))}'; ")
    return "".join(parts)


def resolve_project_dir(agent_cfg: dict, plat_cfg: dict, agent_name: str = "") -> str:
    push = agent_cfg.get("push") or {}
    cwd = (push.get("cwd") or agent_cfg.get("cwd") or "").strip()
    if cwd and not cwd.startswith("/path/"):
        return _to_fs_path(cwd)
    roots = plat_cfg.get("default_project_roots") or {}
    if agent_name and roots.get(agent_name):
        root_val = str(roots[agent_name])
        if not root_val.startswith("/path/"):
            return _to_fs_path(root_val)
    default = (plat_cfg.get("default_project_dir") or "").strip()
    if default and not default.startswith("/path/"):
        return _to_fs_path(default)
    from lib.infra.env_bootstrap import mailbus_paths

    install = Path(mailbus_paths()["root"]).parent
    # Docker 容器内：mailbus 挂载在 /mailbus，parent 为容器根 /，需转 WSL 宿主机路径
    if str(install) == "/" and os.path.exists("/.dockerenv"):
        return os.environ.get("MAILBUS_PROJECT_ROOT", "<PROJECT_ROOT>")
    if resolve_claude_platform(load_mailbus_claude()) == "linux":
        return str(install).replace("\\", "/")
    return str(install).replace("\\", "/")


def _running_in_wsl() -> bool:
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def _running_in_mailbus_docker() -> bool:
    from lib.adapters.plane.platform_runner import running_in_mailbus_docker

    return running_in_mailbus_docker()


def _normalize_windows_path(path: str) -> str:
    """JSON 里 <ROOT>\\ai_tools 会变成 <ROOT>\\a 转义；统一为 <ROOT>/ai_tools。"""
    raw = (path or "").strip()
    if not raw:
        return raw
    if len(raw) >= 2 and raw[1] == ":":
        drive = raw[0].upper()
        rest = raw[2:].lstrip("\\/")
        rest = rest.replace("\\", "/")
        return f"{drive}:/{rest}" if rest else f"{drive}:/"
    return raw.replace("\\", "/")


def resolve_claude_plat_cfg(global_cfg: dict | None = None) -> tuple[str, dict]:
    """Claude 实际运行平台（WSL ttyd 桥接 Windows CLI 时强制 windows 配置）。"""
    global_cfg = global_cfg or {}
    if _use_windows_claude_in_wsl(global_cfg):
        return "windows", platform_settings(global_cfg, "windows")
    plat = resolve_claude_platform(global_cfg)
    return plat, platform_settings(global_cfg, plat)


def _use_windows_claude_in_wsl(global_cfg: dict) -> bool:
    # Docker mailbus 容器内无 /mnt/c，不能走 PowerShell 直启
    from lib.adapters.plane.platform_runner import running_in_mailbus_docker

    if running_in_mailbus_docker():
        if not os.path.isfile(PS_HELPER):
            return False

    configured = (global_cfg.get("platform") or "auto").strip().lower()
    if configured == "windows":
        return True
    if configured == "linux":
        return False

    if not _running_in_wsl() or not os.path.isfile(PS_HELPER):
        return False

    win = platform_settings(global_cfg, "windows")
    lin = platform_settings(global_cfg, "linux")
    win_on = win.get("enabled", True) is not False
    lin_on = lin.get("enabled", True) is not False
    # 典型 Windows+WSL：windows 启用、linux 禁用 → ttyd 桥接 Windows claude（MiniMax 路由）
    if win_on and not lin_on:
        return True
    if win_on and not shutil.which("claude"):
        return True
    return False


def _ps_escape(s: str) -> str:
    return s.replace("'", "''")


def _bash_single_quote(s: str) -> str:
    if not s:
        return "''"
    return "'" + s.replace("'", "'\"'\"'") + "'"


def resolve_ttyd_bin() -> str:
    """解析 ttyd：本机 PATH / 捆绑二进制 / Windows 下走 WSL which ttyd。"""
    for cand in (
        shutil.which("ttyd"),
        os.path.join(ROOT, "docker-agents", "codex-agent", "bin", "ttyd.x86_64"),
        os.path.join(ROOT, "tools", "bin", "ttyd.x86_64"),
    ):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    # Windows Python 通常没有 ttyd；Claude Web 跑在 WSL
    if sys.platform == "win32":
        wsl = shutil.which("wsl.exe") or shutil.which("wsl")
        if wsl:
            try:
                from lib.infra.utils import no_window_creationflags

                r = subprocess.run(
                    [wsl, "-e", "bash", "-lc", "command -v ttyd 2>/dev/null || true"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=no_window_creationflags(),
                )
                path = (r.stdout or "").strip().splitlines()
                path = path[-1].strip() if path else ""
                if path.startswith("/") and r.returncode == 0:
                    return path  # WSL 路径，调用方应经 wsl bash 使用
            except (OSError, subprocess.TimeoutExpired):
                pass
    raise Fatal(
        "ttyd not found. Install in WSL: sudo apt install ttyd "
        f"or ensure {ROOT}/docker-agents/codex-agent/bin/ttyd.x86_64 exists",
        code="ttyd_not_found",
        zh=(
            "未找到 ttyd。请在 WSL 执行: sudo apt install ttyd "
            f"或确认存在 {ROOT}/docker-agents/codex-agent/bin/ttyd.x86_64"
        ),
    )
