"""Mailbus Claude Code 启动 — 宿主机 CLI push / 交互 / 平台桥接。"""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from typing import Optional

from .utils import json_read, json_write, to_wsl_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PS_HELPER = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"


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


def resolve_claude_workspace(agent_cfg: dict, plat_cfg: dict, agent_name: str = "") -> str:
    """交互/同步用的项目目录（含独立 CLAUDE.md，默认同 push.cwd 下的 .mailbus/claude/<agent>）。"""
    roots = plat_cfg.get("claude_workspace_roots") or {}
    if agent_name and roots.get(agent_name):
        return _normalize_windows_path(str(roots[agent_name]))
    base = resolve_project_dir(agent_cfg, plat_cfg, agent_name)
    if agent_name:
        return _normalize_windows_path(f"{base.rstrip('/')}/.mailbus/claude/{agent_name}")
    return base


def _claude_settings_path(claude_home: str) -> str:
    home = _normalize_windows_path(claude_home)
    if len(home) >= 2 and home[1] == ":":
        return home.replace("/", os.sep) + os.sep + "settings.json"
    return os.path.join(home, "settings.json")


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
    os.makedirs(_claude_settings_path(agent_home).rsplit(os.sep, 1)[0], exist_ok=True)

    settings: dict = {}
    base_settings = _claude_settings_path(base_home)
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

    target = _claude_settings_path(agent_home)
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
    extra = (claude_cfg.get("interactive_flags") or claude_cfg.get("push_flags") or "").strip()
    if extra:
        parts.append(extra)
    elif agent_name == "lingyan" and permission == "dontAsk":
        parts.append(f"--allowedTools {_flag_quote_value('Bash,Read,Glob,Grep')}")
    return " ".join(parts)


def _sync_claude_agent_context(agent_name: str, data_dir: str) -> None:
    sync_py = os.path.join(ROOT, "tools", "sync-claude-agent-context.py")
    dd = os.path.abspath(data_dir)
    if not os.path.isfile(sync_py):
        return
    try:
        subprocess.run(
            [sys.executable, sync_py, agent_name, "--data-dir", dd],
            capture_output=True,
            timeout=45,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


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
        f"$env:CLAUDE_CONFIG_DIR='{_ps_escape(claude_home)}'; "
        f"Set-Location '{_ps_escape(workspace)}'; "
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
        return _normalize_windows_path(cwd)
    roots = plat_cfg.get("default_project_roots") or {}
    if agent_name and roots.get(agent_name):
        return _normalize_windows_path(str(roots[agent_name]))
    default = (plat_cfg.get("default_project_dir") or "").strip()
    if default:
        return _normalize_windows_path(default)
    return "/mnt/e/ai_tools" if resolve_claude_platform(load_mailbus_claude()) == "linux" else r"E:/ai_tools"


def _model_flag(agent_cfg: dict, agent_types: dict, model_alias: Optional[str]) -> str:
    from .agent_adapters import model_flag, _flag_value

    if agent_cfg.get("model"):
        return f"--model {agent_cfg['model']}"
    raw = model_flag(agent_cfg, agent_types, "claude_code", model_alias)
    mid = _flag_value(raw, "--model ", "-m ")
    return f"--model {mid}" if mid else ""


def _claude_push_permission(agent_name: str, agent_cfg: dict) -> str:
    claude_cfg = agent_cfg.get("claude") or {}
    permission = (claude_cfg.get("permission_mode") or "").strip()
    if not permission:
        permission = "dontAsk" if agent_name == "lingyan" else "acceptEdits"
    return permission


def _claude_push_argv(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    model_alias: Optional[str],
    prompt: str,
    *,
    model_name: Optional[str] = None,
) -> list[str]:
    """Claude push 参数列表（prompt 为独立 argv，不经 shell 转义）。"""
    permission = _claude_push_permission(agent_name, agent_cfg)
    argv: list[str] = [
        "-p",
        prompt,
        "--permission-mode",
        permission,
        "--output-format",
        "json",
    ]
    if model_name:
        argv.extend(["--model", model_name])
    else:
        mflag = _model_flag(agent_cfg, agent_types, model_alias)
        if mflag:
            argv.extend(shlex.split(mflag))
    max_turns = agent_cfg.get("max_turns")
    if max_turns is not None:
        argv.extend(["--max-turns", str(int(max_turns))])
    claude_cfg = agent_cfg.get("claude") or {}
    extra = (claude_cfg.get("push_flags") or "").strip()
    if extra:
        argv.extend(shlex.split(extra))
    elif agent_name == "lingyan" and permission == "dontAsk":
        argv.extend(["--allowedTools", "Bash,Read,Glob,Grep"])
    return argv


def _claude_push_flags(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    model_alias: Optional[str],
) -> str:
    permission = _claude_push_permission(agent_name, agent_cfg)
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
    claude_cfg = agent_cfg.get("claude") or {}
    extra = claude_cfg.get("push_flags") or ""
    if extra.strip():
        parts.append(extra.strip())
    elif agent_name == "lingyan" and permission == "dontAsk":
        parts.append('--allowedTools "Bash,Read,Glob,Grep"')
    return " ".join(parts)


def _claude_executable_argv(claude_bin: str) -> list[str]:
    """Windows 上解析 claude 可执行文件（.ps1/.cmd/.exe）。"""
    norm = _normalize_windows_path(claude_bin)
    low = norm.lower()
    if low.endswith(".ps1"):
        ps = _powershell_exe()
        if not ps:
            raise RuntimeError("PowerShell 不可用")
        return [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", norm]
    if low.endswith(".cmd") or low.endswith(".bat"):
        comspec = os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe")
        return [comspec, "/c", norm]
    return [norm]


def _push_direct_env(agent_name: str, claude_home: str, data_dir: str) -> dict[str, str]:
    ensure_claude_agent_settings(agent_name, data_dir)
    env = os.environ.copy()
    home = claude_home
    if len(home) >= 2 and home[1] == ":":
        home = home.replace("/", os.sep)
    env["CLAUDE_CONFIG_DIR"] = home
    settings = _read_settings_file(_claude_settings_path(claude_home))
    for key, val in (settings.get("env") or {}).items():
        if val is not None and str(val).strip():
            env[str(key)] = str(val)
    return env


def try_build_push_direct(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    data_dir: str,
    prompt: str,
    model_alias: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Optional[dict]:
    """宿主机直连 claude -p（prompt 独立 argv），避免 shell 嵌套 MSG 引号/换行炸裂。"""
    if (agent_cfg.get("type") or "") != "claude_code":
        return None
    dd = os.path.abspath(data_dir)
    global_cfg = load_mailbus_claude(dd)
    plat, plat_cfg = resolve_claude_plat_cfg(global_cfg)
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
    if plat == "windows":
        claude_bin = resolve_windows_claude_bin(plat_cfg)
    else:
        claude_bin = resolve_claude_bin(plat_cfg) or "claude"
    claude_home = resolve_claude_home(plat_cfg, agent_name)
    project_dir = resolve_project_dir(agent_cfg, plat_cfg, agent_name)
    claude_argv = _claude_push_argv(
        agent_name,
        agent_cfg,
        agent_types,
        model_alias,
        prompt,
        model_name=model_name,
    )
    cwd = project_dir
    if len(cwd) >= 2 and cwd[1] == ":":
        cwd = cwd.replace("/", os.sep)
    return {
        "argv": _claude_executable_argv(claude_bin) + claude_argv,
        "cwd": cwd,
        "env": _push_direct_env(agent_name, claude_home, dd),
    }


def parse_model_name_from_push_template(cmd_template: str) -> Optional[str]:
    """从 build_push_command 模板提取 --model 值（多模型 fallback 用）。"""
    m = re.search(r"--model\s+([^\s']+)", cmd_template or "")
    if not m:
        return None
    return m.group(1).strip("'\"")


def _running_in_wsl() -> bool:
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


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
    if resolve_claude_platform(global_cfg) == "windows":
        return True
    return _running_in_wsl() and not shutil.which("claude")


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
    claude_home = resolve_claude_home(plat_cfg, agent_name)
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
    """WSL/ Linux 下 ttyd 可执行文件（系统 PATH 或 codex-agent 内置）。"""
    for cand in (
        shutil.which("ttyd"),
        os.path.join(ROOT, "docker-agents", "codex-agent", "bin", "ttyd.x86_64"),
        os.path.join(ROOT, "tools", "bin", "ttyd.x86_64"),
    ):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
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


def launch_claude_cli(agent_key: str, data_dir: str) -> dict:
    """启动 Claude Code 交互 CLI（Windows 弹 PowerShell 窗口）。"""
    dd = os.path.abspath(data_dir)
    cfg = json_read(os.path.join(dd, "config.json"), {})
    agents = cfg.get("agents") or {}
    if agent_key not in agents:
        raise ValueError(f"unknown agent: {agent_key}")
    agent_cfg = agents[agent_key]
    if agent_cfg.get("type") != "claude_code":
        raise ValueError(f"agent '{agent_key}' is not claude_code")
    agent_types = cfg.get("agent_types") or {}
    _sync_claude_agent_context(agent_key, dd)
    global_cfg = load_mailbus_claude(dd)
    plat, plat_cfg = resolve_claude_plat_cfg(global_cfg)
    workspace = resolve_claude_workspace(agent_cfg, plat_cfg, agent_key)
    claude_home = resolve_claude_home(plat_cfg, agent_key)

    if plat == "windows":
        inner = _build_interactive_ps_inner(agent_key, agent_cfg, agent_types, dd)
        _spawn_powershell_interactive(inner)
        return {
            "agent": agent_key,
            "kind": "claude_cli",
            "platform": plat,
            "workspace": workspace,
            "claude_home": claude_home,
            "command": inner,
        }

    cmd = build_interactive_command(agent_key, agent_cfg, agent_types, data_dir=dd)
    if _runtime_os() == "windows":
        wsl = _wsl_exe()
        if not wsl:
            raise RuntimeError("wsl.exe 不可用")
        subprocess.run([wsl, "-e", "bash", "-lc", cmd], timeout=30, check=False)
    else:
        subprocess.Popen(["bash", "-lc", cmd])

    return {
        "agent": agent_key,
        "kind": "claude_cli",
        "platform": plat,
        "workspace": workspace,
        "claude_home": claude_home,
        "command": cmd,
    }


def launch_interactive_desktop(agent_key: str, data_dir: str, desktop: dict) -> dict:
    cfg = json_read(os.path.join(os.path.abspath(data_dir), "config.json"), {})
    agents = cfg.get("agents") or {}
    if agent_key not in agents:
        raise ValueError(f"unknown agent: {agent_key}")
    agent_cfg = agents[agent_key]
    agent_types = cfg.get("agent_types") or {}
    global_cfg = load_mailbus_claude(data_dir)
    plat, plat_cfg = resolve_claude_plat_cfg(global_cfg)
    workspace = resolve_claude_workspace(agent_cfg, plat_cfg, agent_key)
    cmd = build_interactive_command(agent_key, agent_cfg, agent_types, data_dir=data_dir)

    if plat == "windows":
        inner = _build_interactive_ps_inner(agent_key, agent_cfg, agent_types, data_dir)
        _spawn_powershell_interactive(inner)
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
        "project_dir": workspace,
        "command": cmd,
    }
