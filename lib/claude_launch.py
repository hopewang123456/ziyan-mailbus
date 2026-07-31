"""Mailbus Claude Code 启动 — 宿主机 CLI push / 交互 / 平台桥接。"""

from __future__ import annotations

from lib.adapters.clock import now_dt, now_ts, now_utc_dt
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .utils import json_read, json_write, to_wsl_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PS_HELPER = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
LAUNCH_QUEUE_PREFIX = "__launch_queue__:"


def _default_data_dir() -> str:
    from .constants import MAILBUS_DATA_STR

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


def _sync_claude_agent_context(agent_name: str, data_dir: str) -> None:
    sync_py = os.path.join(ROOT, "tools", "sync-claude-agent-context.py")
    if not os.path.isfile(sync_py):
        return
    try:
        subprocess.run(
            [sys.executable, sync_py, agent_name, "--data-dir", data_dir],
            capture_output=True,
            timeout=45,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


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
            r = subprocess.run(
                [ps, "-NoProfile", "-Command", script],
                capture_output=True,
                timeout=15,
                text=True,
                encoding="utf-8",
                errors="replace",
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
    """每个 agent 独立 CLAUDE_CONFIG_DIR，避免灵云/灵验共用 ~/.claude。"""
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
    if agent_name and workspace and _is_agent_claude_workspace(workspace, agent_name):
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
        permission = "dontAsk" if agent_name == "lingyan" else "acceptEdits"
    display = (agent_cfg.get("name") or agent_name).strip()
    parts = [
        f"--permission-mode {permission}",
        f"--name {_flag_quote_value(display)}",
    ]
    role_prompts = {
        "lingyun": "你是灵云（Claude Code 精细编码执行），不是灵验。",
        "lingyan": "你是灵验（测试工程师），不是灵云。只做测试验证，不写业务功能代码。",
    }
    hint = role_prompts.get(agent_name)
    if hint:
        parts.append(f"--append-system-prompt {_flag_quote_value(hint)}")
    mflag = _model_flag(agent_cfg, agent_types, None)
    if mflag:
        parts.append(mflag)
    extra = (claude_cfg.get("interactive_flags") or "").strip()
    if extra:
        parts.append(extra)
    elif agent_name == "lingyan" and permission == "dontAsk":
        parts.append(f"--allowedTools {_flag_quote_value('Bash,Read,Glob,Grep')}")
    return " ".join(parts)


def _sync_claude_agent_context(agent_name: str, data_dir: str) -> None:
    """Deprecated: profile sync runs via team-pack/tools/sync-team-pack.py at agent startup."""
    return


def _build_interactive_ps_inner(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    data_dir: str,
) -> str:
    """PowerShell -Command 内联脚本（PATH + env + cd + claude）。"""
    global_cfg = load_mailbus_claude(data_dir)
    _, plat_cfg = resolve_claude_plat_cfg(global_cfg)
    claude_home = resolve_claude_home(plat_cfg, agent_name)
    workspace = resolve_claude_workspace(agent_cfg, plat_cfg, agent_name)
    workspace_ps = _to_powershell_path(workspace)
    claude_home_ps = _to_powershell_path(claude_home)
    cli_flags = _interactive_claude_flags(agent_name, agent_cfg, agent_types)
    agent_label = (agent_cfg.get("name") or agent_name).strip()

    ensure_claude_agent_settings(agent_name, data_dir)
    env_prefix = _powershell_env_from_settings(agent_name, data_dir)
    claude_bin = resolve_windows_claude_bin(plat_cfg)
    claude_inv = (
        f"& '{_ps_escape(claude_bin)}' {cli_flags}"
        if len(claude_bin) >= 2 and claude_bin[1] == ":"
        else f"& {claude_bin} {cli_flags}"
    )
    return (
        f"{_powershell_path_prefix()}"
        f"{env_prefix}"
        f"$env:CLAUDE_CONFIG_DIR='{_ps_escape(claude_home_ps)}'; "
        f"Set-Location '{_ps_escape(workspace_ps)}'; "
        f"Write-Host '=== mailbus agent: {agent_label} ({agent_name}) ===' -ForegroundColor Cyan; "
        f"{claude_inv}"
    )


def _spawn_powershell_interactive(inner: str) -> None:
    """弹出新的 Windows PowerShell 窗口执行 inner 脚本。"""
    ps_exe = _powershell_exe()
    if not ps_exe:
        raise RuntimeError("PowerShell 不可用")
    if sys.platform == "win32":
        subprocess.Popen(
            [ps_exe, "-NoProfile", "-NoExit", "-Command", inner],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return
    win_ps = PS_HELPER if os.path.isfile(PS_HELPER) else ps_exe
    win_path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    arg_inner = inner.replace("'", "''")
    starter = (
        f"Start-Process -FilePath '{win_path}' "
        f"-ArgumentList '-NoExit','-NoProfile','-Command','{arg_inner}'"
    )
    subprocess.run([win_ps, "-NoProfile", "-Command", starter], timeout=30, check=False)


def resolve_project_dir(agent_cfg: dict, plat_cfg: dict, agent_name: str = "") -> str:
    push = agent_cfg.get("push") or {}
    cwd = (push.get("cwd") or agent_cfg.get("cwd") or "").strip()
    if cwd:
        return _to_fs_path(cwd)
    roots = plat_cfg.get("default_project_roots") or {}
    if agent_name and roots.get(agent_name):
        return _to_fs_path(str(roots[agent_name]))
    default = (plat_cfg.get("default_project_dir") or "").strip()
    if default:
        return _to_fs_path(default)
    from .env_bootstrap import mailbus_paths

    install = Path(mailbus_paths()["root"]).parent
    if resolve_claude_platform(load_mailbus_claude()) == "linux":
        return str(install).replace("\\", "/")
    return str(install).replace("\\", "/")


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
        permission = "dontAsk" if agent_name == "lingyan" else "acceptEdits"

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
        default_tools = "Bash,Read,Glob,Grep"
        if agent_name == "lingyun":
            default_tools = "Bash,Read,Write,Glob,Grep,Edit"
        parts.append(f'--allowedTools "{default_tools}"')
    return " ".join(parts)


def _running_in_wsl() -> bool:
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def _running_in_mailbus_docker() -> bool:
    from .platform_runner import running_in_mailbus_docker

    return running_in_mailbus_docker()


def enqueue_launch_queue(cmd: str, title: str, *, mode: str = "") -> bool:
    """Docker 内经 launch-queue 让 WSL 宿主机执行命令（与 launch-agent.sh 同路径）。"""
    candidates = [
        os.environ.get("MAILBUS_LAUNCH_QUEUE", "").strip(),
        "/mailbus/run/launch-queue",
        os.path.join(ROOT, "run", "launch-queue"),
    ]
    safe_title = re.sub(r"[^\w.-]+", "-", (title or "push").strip())[:40] or "push"
    for queue_dir in candidates:
        if not queue_dir:
            continue
        try:
            os.makedirs(queue_dir, exist_ok=True)
            path = os.path.join(queue_dir, f"{safe_title}-{int(now_ts())}.launch")
            with open(path, "w", encoding="utf-8") as f:
                f.write((cmd or "").strip() + "\n")
                f.write(safe_title + "\n")
                if mode:
                    f.write(mode.strip() + "\n")
            try:
                os.chmod(path, 0o666)
            except OSError:
                pass
            return True
        except OSError:
            continue
    return False


def _build_docker_queue_push(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    model_alias: Optional[str],
    *,
    data_dir: str,
) -> str:
    """Docker scheduler scan：经 launch-queue 在 WSL 宿主机跑 PowerShell claude -p。"""
    global_cfg = load_mailbus_claude(data_dir)
    plat_cfg = platform_settings(global_cfg, "windows")
    claude_bin = resolve_windows_claude_bin(plat_cfg)
    claude_home = resolve_claude_home(plat_cfg, agent_name)
    project_dir = resolve_project_dir(agent_cfg, plat_cfg, agent_name)
    flags = _claude_push_flags(agent_name, agent_cfg, agent_types, model_alias)
    ps_inner = (
        _powershell_path_prefix()
        + f"$env:USERPROFILE = Split-Path -Parent '{_ps_escape(claude_home)}'; "
        f"Set-Location '{_ps_escape(project_dir)}'; "
        f"& {claude_bin} {flags}"
    )
    ps_exe = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    wsl_cmd = (
        f"nohup {ps_exe} -NoProfile -Command {_bash_single_quote(ps_inner)} "
        f">> /tmp/mailbus-push-{agent_name}.log 2>&1 &"
    )
    return f"{LAUNCH_QUEUE_PREFIX}{wsl_cmd}"


def _normalize_windows_path(path: str) -> str:
    """JSON 里 E:\\ai_tools 会变成 E:\\a 转义；统一为 E:/ai_tools。"""
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
    from .platform_runner import running_in_mailbus_docker

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


def _build_windows_push(claude_bin: str, project_dir: str, flags: str, claude_home: str) -> str:
    ps_exe = _powershell_exe()
    if not ps_exe:
        raise RuntimeError("PowerShell 不可用，无法桥接 Windows Claude Code")
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
    if _runtime_os() == "windows":
        wsl = _wsl_exe()
        if not wsl:
            raise RuntimeError("wsl.exe 不可用，无法桥接 Linux Claude Code")
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
) -> list[str]:
    """构建 claude -p 的 argv 片段（不含可执行文件路径）。"""
    claude_cfg = agent_cfg.get("claude") or {}
    permission = (claude_cfg.get("permission_mode") or "").strip()
    if not permission:
        permission = "dontAsk" if agent_name == "lingyan" else "acceptEdits"

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
    extra = (claude_cfg.get("push_flags") or "").strip()
    if extra:
        parts.extend(shlex.split(extra, posix=False))
    elif permission == "dontAsk":
        default_tools = "Bash,Read,Glob,Grep"
        if agent_name == "lingyun":
            default_tools = "Bash,Read,Write,Glob,Grep,Edit"
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
    """Claude Code 直连 argv（委托 lib.agent_push，保留兼容导入）。"""
    from .agent_push import try_build_push_direct as _push_direct

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
            subprocess.run(
                [sys.executable, sync_py, agent_name, "--data-dir", dd],
                capture_output=True,
                timeout=45,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass
    global_cfg = load_mailbus_claude(data_dir)
    plat = resolve_claude_platform(global_cfg)
    if not _platform_enabled(global_cfg, plat):
        alt = "linux" if plat == "windows" else "windows"
        if _platform_enabled(global_cfg, alt):
            plat = alt
    plat_cfg = platform_settings(global_cfg, plat)
    claude_bin = resolve_claude_bin(plat_cfg)
    claude_home = resolve_claude_home(plat_cfg)
    project_dir = resolve_project_dir(agent_cfg, plat_cfg, agent_name)
    flags = _claude_push_flags(agent_name, agent_cfg, agent_types, model_alias)
    if plat == "windows":
        return _build_windows_push(claude_bin, project_dir, flags, claude_home)
    return _build_linux_push(claude_bin, project_dir, flags, claude_home)


def build_interactive_command(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    data_dir: str | None = None,
) -> str:
    dd = data_dir or _default_data_dir()
    _sync_claude_agent_context(agent_name, dd)
    global_cfg = load_mailbus_claude(dd)
    plat, plat_cfg = resolve_claude_plat_cfg(global_cfg)
    claude_bin = resolve_claude_bin(plat_cfg)
    claude_home = resolve_claude_home(plat_cfg, agent_name)
    workspace = resolve_claude_workspace(agent_cfg, plat_cfg, agent_name)
    cli_flags = _interactive_claude_flags(agent_name, agent_cfg, agent_types)

    if plat == "windows":
        inner = _build_interactive_ps_inner(agent_name, agent_cfg, agent_types, dd)
        ps_exe = _powershell_exe()
        if sys.platform == "win32":
            return f'"{ps_exe}" -NoProfile -NoExit -Command "{inner}"'
        return f"{_bash_single_quote(ps_exe)} -NoProfile -NoExit -Command {_bash_single_quote(inner)}"

    inner = (
        f"cd {shlex.quote(to_wsl_path(workspace))} && "
        f"CLAUDE_CONFIG_DIR={shlex.quote(to_wsl_path(claude_home))} "
        f"{shlex.quote(claude_bin)} {cli_flags}"
    )
    if _runtime_os() == "windows":
        wsl = _wsl_exe()
        return f"{shlex.quote(wsl)} -e bash -lc {_bash_single_quote(inner)}"
    return f"bash -lc {_bash_single_quote(inner)}"


def build_interactive_shell_inner(
    agent_name: str,
    data_dir: str,
    *,
    platform: str = "linux",
) -> str:
    """WSL/ttyd 内直接执行的 bash 一行命令（无 PowerShell 包装）。"""
    cfg = json_read(os.path.join(os.path.abspath(data_dir), "config.json"), {})
    agents = cfg.get("agents") or {}
    if agent_name not in agents:
        raise ValueError(f"unknown agent: {agent_name}")
    agent_cfg = agents[agent_name]
    agent_types = cfg.get("agent_types") or {}
    global_cfg = load_mailbus_claude(data_dir)
    use_windows = _use_windows_claude_in_wsl(global_cfg)
    _, plat_cfg = resolve_claude_plat_cfg(global_cfg)
    claude_home = resolve_claude_home(plat_cfg, agent_name)
    workspace = resolve_claude_workspace(agent_cfg, plat_cfg, agent_name)
    cli_flags = _interactive_claude_flags(agent_name, agent_cfg, agent_types)
    agent_label = (agent_cfg.get("name") or agent_name).strip()

    _sync_claude_agent_context(agent_name, data_dir)

    if use_windows:
        ps_exe = PS_HELPER if os.path.isfile(PS_HELPER) else "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        inner = _build_interactive_ps_inner(agent_name, agent_cfg, agent_types, data_dir)
        return f"{shlex.quote(ps_exe)} -NoProfile -NoExit -Command {shlex.quote(inner)}"

    project_dir = to_wsl_path(workspace)
    claude_home_wsl = to_wsl_path(claude_home)
    claude_bin = resolve_claude_bin(plat_cfg)
    return (
        f"echo '=== mailbus agent: {agent_label} ({agent_name}) ==='; "
        f"cd {shlex.quote(project_dir)} && "
        f"CLAUDE_CONFIG_DIR={shlex.quote(claude_home_wsl)} "
        f"exec {shlex.quote(claude_bin)} {cli_flags}"
    )


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
                r = subprocess.run(
                    [wsl, "-e", "bash", "-lc", "command -v ttyd 2>/dev/null || true"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    encoding="utf-8",
                    errors="replace",
                )
                path = (r.stdout or "").strip().splitlines()
                path = path[-1].strip() if path else ""
                if path.startswith("/") and r.returncode == 0:
                    return path  # WSL 路径，调用方应经 wsl bash 使用
            except (OSError, subprocess.TimeoutExpired):
                pass
    raise RuntimeError(
        "未找到 ttyd。请在 WSL 执行: sudo apt install ttyd "
        f"或确认存在 {ROOT}/docker-agents/codex-agent/bin/ttyd.x86_64"
    )


def host_ps_output() -> str:
    try:
        if sys.platform == "win32":
            ps = _powershell_exe()
            if ps:
                r = subprocess.run(
                    [ps, "-NoProfile", "-Command",
                     "Get-CimInstance Win32_Process | Select-Object -ExpandProperty CommandLine"],
                    capture_output=True,
                    text=True,
                    timeout=12,
                    encoding="utf-8",
                    errors="replace",
                )
                if r.returncode == 0:
                    return r.stdout or ""
        r = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if r.returncode == 0:
            return r.stdout or ""
    except Exception:
        pass
    return ""


def host_cli_active(ps_output: str) -> bool:
    noise = ("grep", "Get-CimInstance", "powershell -NoProfile")
    pat = re.compile(r"\bclaude\b.*(-p\b|--print\b)|(-p\b|--print\b).*\bclaude\b")
    for line in ps_output.splitlines():
        low = line.lower()
        if any(n in low for n in noise):
            continue
        if pat.search(line):
            return True
    return False


def launch_interactive_desktop(agent_key: str, data_dir: str, desktop: dict) -> dict:
    cfg = json_read(os.path.join(os.path.abspath(data_dir), "config.json"), {})
    agents = cfg.get("agents") or {}
    if agent_key not in agents:
        raise ValueError(f"unknown agent: {agent_key}")
    agent_cfg = agents[agent_key]
    agent_types = cfg.get("agent_types") or {}
    global_cfg = load_mailbus_claude(data_dir)
    plat = resolve_claude_platform(global_cfg)
    plat_cfg = platform_settings(global_cfg, plat)
    project_dir = (
        desktop.get("project_dir")
        or resolve_project_dir(agent_cfg, plat_cfg, agent_key)
    )
    claude_bin = resolve_claude_bin(plat_cfg)
    cmd = build_interactive_command(agent_key, agent_cfg, agent_types, data_dir=data_dir)

    if plat == "windows":
        ps_exe = _powershell_exe()
        if not ps_exe:
            raise RuntimeError("PowerShell 不可用")
        ps_script = f"Start-Process -FilePath '{_ps_escape(ps_exe)}' -ArgumentList '-NoExit','-NoProfile','-Command','Set-Location ''{_ps_escape(project_dir)}''; {claude_bin}'"
        subprocess.run([ps_exe, "-NoProfile", "-Command", ps_script], timeout=30, check=False)
    else:
        term_cmds = [
            f"gnome-terminal -- bash -lc {shlex.quote(cmd)}",
            f"xterm -e bash -lc {shlex.quote(cmd)}",
            cmd,
        ]
        launched = False
        for tc in term_cmds:
            try:
                subprocess.run(["bash", "-lc", tc], timeout=30, check=False)
                launched = True
                break
            except Exception:
                continue
        if not launched:
            raise RuntimeError("无法启动交互式 Claude Code 终端")

    return {
        "agent": agent_key,
        "kind": "claude_interactive",
        "platform": plat,
        "project_dir": project_dir,
        "command": cmd,
    }


def launch_claude_cli(agent_key: str, data_dir: str) -> dict:
    """启动 Claude Code 交互 CLI（Windows/WSL 窗口或 Docker launch-queue）。"""
    cfg = json_read(os.path.join(os.path.abspath(data_dir), "config.json"), {})
    agents = cfg.get("agents") or {}
    if agent_key not in agents:
        raise ValueError(f"unknown agent: {agent_key}")
    agent_cfg = agents[agent_key]
    agent_types = cfg.get("agent_types") or {}
    cmd = build_interactive_command(agent_key, agent_cfg, agent_types, data_dir=data_dir)

    if _running_in_mailbus_docker():
        if not enqueue_launch_queue(cmd, agent_key, mode="interactive"):
            raise RuntimeError("launch queue write failed")
        return {"agent": agent_key, "mode": "cli", "status": "queued", "command": cmd}

    global_cfg = load_mailbus_claude(data_dir)
    plat = resolve_claude_platform(global_cfg)
    if plat == "windows" or sys.platform == "win32":
        inner = _build_interactive_ps_inner(agent_key, agent_cfg, agent_types, data_dir)
        _spawn_powershell_interactive(inner)
    elif _wsl_exe() and sys.platform == "win32":
        subprocess.Popen([_wsl_exe(), "-e", "bash", "-lc", cmd], start_new_session=True)
    else:
        subprocess.Popen(["bash", "-lc", cmd], start_new_session=True)

    return {
        "agent": agent_key,
        "mode": "cli",
        "status": "ok",
        "platform": plat,
        "command": cmd,
    }
