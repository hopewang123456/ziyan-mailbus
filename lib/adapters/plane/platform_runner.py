"""跨平台命令执行 — 替代 mailbus 启动脚本中的 bash/bat/PowerShell 胶水层。"""

from __future__ import annotations

from lib.infra.clock import now_dt, now_ts, now_utc_dt
import contextlib
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from lib.infra.env_bootstrap import load_mailbus_env, mailbus_paths
from lib.infra.utils import configure_stdio_utf8, to_wsl_path


LogFn = Callable[[str], None]


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


def detect_platform() -> str:
    """win32 | linux | darwin | wsl"""
    if sys.platform == "win32":
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            if "microsoft" in fh.read().lower():
                return "wsl"
    except OSError:
        pass
    return "linux"


def docker_sock_available() -> bool:
    """docker.sock 是 socket，isfile() 为 False，须用 exists。"""
    return os.path.exists("/var/run/docker.sock")


def running_in_mailbus_docker() -> bool:
    """mailbus serve 跑在 Docker 容器内。"""
    if os.path.isfile("/.dockerenv"):
        return True
    return os.path.isdir("/mailbus/store") and docker_sock_available()


def docker_cli_bridge_available() -> bool:
    """容器内或挂载 docker.sock 时，CLI 应走 launch-queue + WSL watchdog。"""
    return running_in_mailbus_docker() or docker_sock_available()


def default_log(prefix: str, log_path: str) -> LogFn:
    def _log(msg: str) -> None:
        line = f"[{prefix}] {msg}"
        print(line)
        try:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    return _log


def probe_http(
    url: str,
    *,
    timeout: float = 5.0,
    ok_codes: frozenset[int] = frozenset({200}),
    headers: dict[str, str] | None = None,
    accept_codes: frozenset[int] | None = None,
) -> bool:
    """Return True if HTTP status is in ok_codes (or accept_codes if provided)."""
    allowed = accept_codes if accept_codes is not None else ok_codes
    probed = url
    # Docker 容器内 127.0.0.1 指向本容器自身，需要替换为 host.docker.internal
    if os.path.exists("/.dockerenv") and "127.0.0.1" in url:
        probed = url.replace("127.0.0.1", "host.docker.internal")
    try:
        req = urllib.request.Request(probed, headers=dict(headers or {}))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in allowed
    except urllib.error.HTTPError as exc:
        return exc.code in allowed
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return False


def run(
    cmd: Sequence[str],
    *,
    cwd: str | None = None,
    timeout: int | None = None,
    check: bool = False,
    env: dict[str, str] | None = None,
) -> RunResult:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        cwd=cwd,
        env=merged,
        encoding="utf-8",
        errors="replace",
    )
    return RunResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def run_stream(
    cmd: Sequence[str],
    *,
    cwd: str | None = None,
    log: LogFn | None = None,
    timeout: int | None = None,
) -> int:
    # Inherit console stdio as bytes — do NOT force text mode.
    # wsl.exe may emit UTF-16 warnings when stdout is a pipe; text mode
    # turns that into mojibake / broken console sessions near start end.
    proc = subprocess.run(
        list(cmd),
        cwd=cwd,
        timeout=timeout,
    )
    return int(proc.returncode)


def powershell_exe() -> str:
    if sys.platform == "win32":
        windir = os.environ.get("SystemRoot", r"C:\Windows")
        ps = os.path.join(windir, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        if os.path.isfile(ps):
            return ps
    wsl_ps = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    if os.path.isfile(wsl_ps):
        return wsl_ps
    return shutil.which("powershell") or shutil.which("powershell.exe") or ""


def wsl_exe() -> str:
    if detect_platform() == "win32":
        return shutil.which("wsl.exe") or shutil.which("wsl") or ""
    return ""


def win_curl_exe() -> str:
    if sys.platform == "win32":
        windir = os.environ.get("SystemRoot", r"C:\Windows")
        curl = os.path.join(windir, "System32", "curl.exe")
        if os.path.isfile(curl):
            return curl
    wsl_curl = "/mnt/c/Windows/System32/curl.exe"
    if os.path.isfile(wsl_curl):
        return wsl_curl
    return ""


def run_powershell_file(script: str, *args: str, timeout: int = 120) -> RunResult:
    ps = powershell_exe()
    if not ps or not os.path.isfile(script):
        return RunResult(1, "", f"missing powershell or script: {script}")
    cmd = [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, *args]
    return run(cmd, timeout=timeout)


def run_wsl(
    inner: str,
    *,
    distro: str = "Ubuntu",
    cwd: str | None = None,
    timeout: int | None = None,
) -> int:
    wsl = wsl_exe()
    if not wsl:
        return 1
    # Force UTF-8 inside the Linux side so docker/compose tables stay readable.
    wrapped = f"export LANG=C.UTF-8 LC_ALL=C.UTF-8; {inner}"
    cmd = [wsl, "-d", distro, "-e", "bash", "-lc", wrapped]
    return run_stream(cmd, cwd=cwd, timeout=timeout)


def wake_wsl(distro: str = "Ubuntu") -> bool:
    wsl = wsl_exe()
    if not wsl:
        return False
    return run([wsl, "-d", distro, "-e", "true"], timeout=60).returncode == 0


def docker_argv(*args: str) -> list[str]:
    """本机 docker，或 Windows PATH 无 docker 时经 wsl -e docker。"""
    if shutil.which("docker"):
        return ["docker", *args]
    if detect_platform() == "win32":
        wsl = wsl_exe()
        if wsl:
            return [wsl, "-e", "docker", *args]
    return ["docker", *args]


def docker_ready() -> bool:
    try:
        return run(docker_argv("info"), timeout=15).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def ensure_docker(max_wait: int = 90, log: LogFn | None = None) -> bool:
    if docker_ready():
        return True
    plat = detect_platform()
    if plat in ("linux", "wsl"):
        run(["sudo", "service", "docker", "start"], timeout=30)
    deadline = now_ts() + max_wait
    while now_ts() < deadline:
        if docker_ready():
            if log:
                log("Docker ready")
            return True
        time.sleep(2)
    return False


def compose_file_args() -> list[str]:
    """Base compose + optional override generated by mailbus compose sync."""
    load_mailbus_env()
    from pathlib import Path

    root = Path(os.environ.get("MAILBUS_ROOT", Path(__file__).resolve().parents[3]))
    compose_dir = root / "docker-agents"
    files = ["-f", str(compose_dir / "docker-compose.yml")]
    override = compose_dir / "docker-compose.override.yml"
    if override.is_file():
        files.extend(["-f", str(override)])
    return files


def compose_cmd(*args: str, project: str | None = None, cwd: str | None = None) -> list[str]:
    load_mailbus_env()
    proj = project or os.environ.get("COMPOSE_PROJECT_NAME", "docker-agents")
    return [*docker_argv("compose"), "-p", proj, *compose_file_args(), *args]


def docker_container_running(name: str) -> bool:
    r = run(docker_argv("inspect", "-f", "{{.State.Running}}", name), timeout=15)
    return r.returncode == 0 and r.stdout.strip() == "true"


def docker_exec(mailbus_container: str, *inner: str, timeout: int = 120) -> RunResult:
    return run(docker_argv("exec", mailbus_container, *inner), timeout=timeout)


def kill_host_port(port: int, log: LogFn | None = None) -> None:
    """杀掉占用端口的非 Docker 宿主机进程（Linux/WSL）。"""
    if detect_platform() not in ("linux", "wsl"):
        return
    r = run(["ss", "-tlnp"], timeout=10)
    if r.returncode != 0:
        return
    needle = f":{port} "
    pids: set[str] = set()
    for line in r.stdout.splitlines():
        if needle not in line:
            continue
        for m in re.finditer(r"pid=(\d+)", line):
            pids.add(m.group(1))
    for pid in sorted(pids):
        cgroup = f"/proc/{pid}/cgroup"
        try:
            with open(cgroup, encoding="utf-8", errors="replace") as fh:
                if "docker" in fh.read():
                    continue
        except OSError:
            pass
        if log:
            log(f"Killing host process on :{port} pid={pid}")
        with contextlib.suppress(OSError):
            os.kill(int(pid), 15)


def kill_process_pattern(pattern: str) -> None:
    if detect_platform() not in ("linux", "wsl"):
        return
    r = run(["pgrep", "-f", pattern], timeout=10)
    if r.returncode != 0:
        return
    for pid in r.stdout.split():
        with contextlib.suppress(OSError, ValueError):
            os.kill(int(pid), 15)


@contextlib.contextmanager
def flock_lock(lock_path: str):
    """非阻塞文件锁（start-team 防重入）。"""
    import fcntl

    os.makedirs(os.path.dirname(lock_path) or "/tmp", exist_ok=True)
    fd = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        fd.close()
        raise TimeoutError("another instance is running") from exc
    try:
        yield
    finally:
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        fd.close()


def upsert_env_file(path: str, key: str, value: str) -> None:
    lines: list[str] = []
    found = False
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith(f"{key}="):
                    lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"{key}={value}\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def run_legacy_bash(script_name: str, *args: str, log: LogFn | None = None) -> int:
    """过渡期：委托 docker-agents 下尚未迁移的 bash 脚本。"""
    paths = mailbus_paths()
    script = os.path.join(paths["compose_dir"], script_name)
    if not os.path.isfile(script):
        if log:
            log(f"WARNING: missing legacy script {script}")
        return 1
    cmd = ["bash", script, *args]
    if log:
        log(f"delegating → bash {script_name} {' '.join(args)}".rstrip())
    r = run(cmd, cwd=paths["compose_dir"], timeout=900)
    if r.stdout.strip() and log:
        for line in r.stdout.splitlines():
            log(line)
    if r.stderr.strip() and log:
        for line in r.stderr.splitlines():
            log(f"WARN: {line}")
    return r.returncode


def mailbus_py_in_wsl(extra_args: Iterable[str]) -> str:
    paths = mailbus_paths()
    py = to_wsl_path(os.path.join(paths["root"], "tools", "mailbus.py"))
    return f"python3 {py} {' '.join(extra_args)}".strip()


def open_windows_urls(urls: Sequence[str]) -> None:
    if sys.platform != "win32":
        return
    for url in urls:
        run(["cmd", "/c", "start", "", url], timeout=15)


def init_stdio() -> None:
    configure_stdio_utf8()
    load_mailbus_env()
