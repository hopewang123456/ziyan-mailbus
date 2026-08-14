"""Mailbus 团队 Docker 生命周期 — Python 版 start-team / stop-team / wsl-recover。"""

from __future__ import annotations

from lib.infra.clock import now_dt, now_ts, now_utc_dt
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from lib.infra.env_bootstrap import load_mailbus_env, mailbus_paths
from .platform_runner import (
    LogFn,
    RunResult,
    compose_cmd,
    default_log,
    detect_platform,
    docker_container_running,
    docker_exec,
    ensure_docker,
    flock_lock,
    kill_host_port,
    kill_process_pattern,
    mailbus_py_in_wsl,
    probe_http,
    run,
    run_legacy_bash,
    run_stream,
    run_wsl,
    upsert_env_file,
    wake_wsl,
    win_curl_exe,
    wsl_exe,
)
from .post_start import (
    apply_codex_ui,
    ensure_claude_agents,
    fix_openclaw_gateways,
    fix_portproxy,
    smoke_test,
    stop_claude_agents,
    uninstall_mailbus_cron,
)


def _proxy_sensitive_services(data_dir: str) -> list[str]:
    """从 config.json agents 的 docker.compose_service 推导代理敏感容器。"""
    import json

    services: list[str] = []
    cfg_path = os.path.join(data_dir, "config.json")
    try:
        if os.path.isfile(cfg_path):
            cfg = json.load(open(cfg_path, encoding="utf-8"))
            for ac in (cfg.get("agents") or {}).values():
                svc = (ac.get("docker") or {}).get("compose_service")
                if svc and str(svc).strip() not in services:
                    services.append(str(svc).strip())
    except (OSError, json.JSONDecodeError):
        pass
    return services or ["hermes", "openclaw"]


def _api_base(port: str | None = None) -> str:
    p = port or mailbus_paths()["api_port"]
    return f"http://127.0.0.1:{p}"


def setup_container_proxy(log: LogFn | None = None) -> str:
    """根据 Windows 系统代理开关写入 docker-agents/.env（原 setup-container-proxy.sh）。"""
    paths = mailbus_paths()
    env_file = os.path.join(paths["compose_dir"], ".env")
    proxy_state = os.path.join(paths["compose_dir"], ".proxy-state")
    clash_port = os.environ.get("CLASH_PORT", "7897")

    win_host = ""
    r = run(["ip", "route", "show", "default"], timeout=10)
    if r.returncode == 0:
        parts = r.stdout.split()
        if len(parts) >= 3:
            win_host = parts[2]

    proxy_enable = "0"
    ps = __import__("lib.adapters.plane.platform_runner", fromlist=["powershell_exe"]).powershell_exe()
    if ps:
        pr = run(
            [
                ps,
                "-NoProfile",
                "-Command",
                "(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings').ProxyEnable",
            ],
            timeout=15,
        )
        proxy_enable = (pr.stdout or "0").strip().replace("\r", "")

    container_proxy = ""
    if proxy_enable == "1" and win_host:
        test = run(
            [
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "--connect-timeout",
                "3",
                "-x",
                f"http://{win_host}:{clash_port}",
                "https://api.deepseek.com/v1/models",
            ],
            timeout=15,
        )
        if test.returncode == 0:
            container_proxy = f"http://{win_host}:{clash_port}"

    os.makedirs(os.path.dirname(env_file), exist_ok=True)
    if not os.path.isfile(env_file):
        open(env_file, "a", encoding="utf-8").close()
    upsert_env_file(env_file, "CONTAINER_HTTP_PROXY", container_proxy)
    upsert_env_file(env_file, "CONTAINER_HTTPS_PROXY", container_proxy)
    with open(proxy_state, "w", encoding="utf-8") as fh:
        fh.write(container_proxy)

    if log:
        if container_proxy:
            log(f"Windows system proxy ON → containers use {container_proxy}")
        else:
            log("Windows system proxy OFF or Clash unreachable → direct connection")
    return container_proxy


def ensure_ollama_wsl_proxy(action: str = "start", log: LogFn | None = None) -> int:
    """WSL Ollama 代理（原 ensure-ollama-wsl-proxy.sh）。"""
    paths = mailbus_paths()
    pid_file = "/tmp/ollama-wsl-proxy.pid"
    log_path = "/tmp/ollama-wsl-proxy.log"
    proxy_py = os.path.join(paths["root"], "tools", "ollama-wsl-proxy.py")
    wait_seconds = int(os.environ.get("OLLAMA_WSL_PROXY_WAIT_SECONDS", "90"))
    try:
        from lib.adapters.ops.service_registry import ollama_proxy_listen

        listen_host, listen_port, target = ollama_proxy_listen(data_dir=paths.get("data_dir") or "")
    except Exception:
        listen_host, listen_port, target = "0.0.0.0", int(os.environ.get("OLLAMA_WSL_PROXY_PORT", "11435")), "http://127.0.0.1:11434"

    def _stop() -> None:
        if not os.path.isfile(pid_file):
            return
        try:
            with open(pid_file, encoding="utf-8") as fh:
                pid = int(fh.read().strip())
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
        except (OSError, ValueError):
            pass
        with contextlib.suppress(OSError):
            os.remove(pid_file)

    if action == "stop":
        _stop()
        return 0

    if action == "restart":
        _stop()
        action = "start"

    if action == "status":
        if os.path.isfile(pid_file):
            try:
                with open(pid_file, encoding="utf-8") as fh:
                    pid = int(fh.read().strip())
                os.kill(pid, 0)
                print(f"running pid={pid} :{listen_port}")
                return 0
            except OSError:
                print("stopped")
                return 1
        print("stopped")
        return 1

    if not os.path.isfile(proxy_py):
        if log:
            log(f"WARNING: missing {proxy_py}")
        return 1

    curl = win_curl_exe()
    if curl:
        deadline = now_ts() + wait_seconds
        while now_ts() < deadline:
            if run(
                [curl, "-sf", "--noproxy", "*", "--max-time", "3", f"{target}/api/tags"],
                timeout=10,
            ).returncode == 0:
                break
            time.sleep(1)
        else:
            if log:
                log(f"Windows Ollama not ready after {wait_seconds}s — skip proxy")
            return 1

    _stop()
    env = os.environ.copy()
    env["OLLAMA_WSL_PROXY_TARGET"] = target
    env["OLLAMA_WSL_PROXY_PORT"] = str(listen_port)
    with open(log_path, "a", encoding="utf-8") as logfh:
        proc = subprocess.Popen(
            ["python3", proxy_py, "--host", listen_host, "--port", str(listen_port)],
            stdout=logfh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    with open(pid_file, "w", encoding="utf-8") as fh:
        fh.write(str(proc.pid))
    time.sleep(1)
    if probe_http(f"http://127.0.0.1:{listen_port}/api/tags", timeout=5):
        if log:
            log(f"ollama-wsl-proxy OK pid={proc.pid} :{listen_port} -> {target}")
        return 0
    _stop()
    if log:
        log(f"ollama-wsl-proxy failed — see {log_path}")
    return 1


def _prepare_watchdog_queue(log: LogFn | None = None) -> str:
    """清理 stale watchdog 进程并确保 launch-queue 目录可写。"""
    paths = mailbus_paths()
    compose = paths["compose_dir"]
    watchdog = os.path.join(compose, "mailbus-launch-watchdog.sh")
    qdir = os.path.join(paths["run_dir"], "launch-queue")
    os.makedirs(qdir, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(qdir, 0o777)
    kill_process_pattern(watchdog)
    if log:
        log(f"[watchdog] queue ready at {qdir}, stale watchdogs cleared")
    return qdir


def run_watchdog_foreground() -> int:
    """前台运行 launch watchdog（供 systemd ExecStart 使用）。"""
    paths = mailbus_paths()
    compose = paths["compose_dir"]
    watchdog = os.path.join(compose, "mailbus-launch-watchdog.sh")
    if not os.path.isfile(watchdog):
        print(f"[watchdog] missing {watchdog}", file=sys.stderr)
        return 1
    qdir = _prepare_watchdog_queue()
    env = os.environ.copy()
    env["MAILBUS_LAUNCH_QUEUE"] = qdir
    os.execvpe("bash", ["bash", watchdog], env)
    return 1  # unreachable


WATCHDOG_PID_FILE = "/tmp/mailbus-watchdog.pid"
WATCHDOG_PGREP = "mailbus-launch-watchdog\\.sh"


def _watchdog_running() -> bool:
    r = run(["pgrep", "-f", WATCHDOG_PGREP], timeout=10)
    if r.returncode == 0 and (r.stdout or "").strip():
        return True
    if os.path.isfile(WATCHDOG_PID_FILE):
        try:
            with open(WATCHDOG_PID_FILE, encoding="utf-8") as fh:
                pid = int(fh.read().strip())
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            with contextlib.suppress(OSError):
                os.remove(WATCHDOG_PID_FILE)
    return False


def restart_watchdog(log: LogFn | None = None) -> int:
    """重启 launch watchdog（Python 内联原 restart-watchdog-root.sh 逻辑）。"""
    if detect_platform() == "win32":
        return run_wsl(mailbus_py_in_wsl(["watchdog", "restart"]), timeout=120)

    paths = mailbus_paths()
    compose = paths["compose_dir"]
    watchdog = os.path.join(compose, "mailbus-launch-watchdog.sh")
    qdir = _prepare_watchdog_queue(log)
    os.environ["MAILBUS_LAUNCH_QUEUE"] = qdir

    def _run_in_wsl(cmd: list[str]) -> RunResult:
        if detect_platform() == "wsl":
            return run(cmd, timeout=30)
        wsl = wsl_exe()
        if not wsl:
            return RunResult(1, "", "wsl not found")
        return run([wsl, "-d", "Ubuntu", "-e", *cmd], timeout=30)

    def _systemd_ok() -> bool:
        r = _run_in_wsl(["systemctl", "show", "mailbus-watchdog", "-p", "ExecStart", "--value"])
        out = r.stdout or ""
        return "mailbus.py watchdog run" in out or "mailbus-launch-watchdog.sh" in out

    def _try_systemd() -> bool:
        if _run_in_wsl(["systemctl", "is-enabled", "mailbus-watchdog"]).returncode != 0:
            return False
        if not _systemd_ok():
            if log:
                log("WARN: mailbus-watchdog.service ExecStart outdated — run install-mailbus-watchdog-service.sh")
            return False
        if _run_in_wsl(["systemctl", "is-active", "mailbus-watchdog"]).returncode == 0:
            if log:
                log("Watchdog already running via systemd")
            return True
        for cmd in (
            ["sudo", "-n", "systemctl", "restart", "mailbus-watchdog"],
            ["sudo", "-n", "systemctl", "start", "mailbus-watchdog"],
            ["systemctl", "restart", "mailbus-watchdog"],
            ["systemctl", "start", "mailbus-watchdog"],
        ):
            if _run_in_wsl(cmd).returncode == 0:
                time.sleep(1)
                if _run_in_wsl(["systemctl", "is-active", "mailbus-watchdog"]).returncode == 0:
                    if log:
                        log("Watchdog started via systemd")
                    return True
        return False

    if _try_systemd():
        return 0

    if _watchdog_running():
        if log:
            log("Watchdog already running (pgrep/pid)")
        return 0

    kill_process_pattern(WATCHDOG_PGREP)
    time.sleep(1)
    env = os.environ.copy()
    env["MAILBUS_LAUNCH_QUEUE"] = qdir
    log_path = "/tmp/mailbus-watchdog.log"
    with open(log_path, "a", encoding="utf-8") as logfh:
        proc = subprocess.Popen(
            ["bash", watchdog],
            stdout=logfh,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
            cwd=compose,
        )
    with open(WATCHDOG_PID_FILE, "w", encoding="utf-8") as fh:
        fh.write(str(proc.pid))

    for attempt in range(5):
        time.sleep(1)
        if _watchdog_running():
            if log:
                log(f"Watchdog started via nohup pid={proc.pid} (log: {log_path})")
            return 0
        if proc.poll() is not None:
            break

    if log:
        log(f"WARNING: watchdog failed to start (exit={proc.poll()}) — see {log_path}")
        tail = run(["tail", "-5", log_path], timeout=5)
        if tail.stdout.strip():
            log(tail.stdout.strip())
    with contextlib.suppress(OSError):
        os.remove(WATCHDOG_PID_FILE)
    return 1


def _ensure_windows_ollama(log: LogFn | None = None) -> None:
    paths = mailbus_paths()
    py = os.path.join(paths["root"], "tools", "ensure-ollama.py")
    data = paths["data_dir"]
    if not os.path.isfile(py):
        if log:
            log(f"WARNING: missing {py}")
        return
    r = run(
        [sys.executable, py, "--data-dir", data, "--no-pull", "--wait-seconds", "90"],
        timeout=120,
    )
    if r.returncode != 0 and log:
        log("WARNING: ensure-ollama failed — internal LLM may fall back to remote")


def _sync_layers(log: LogFn | None = None) -> None:
    """Default: do NOT mass-sync skills into agent workspaces (plan: Vault SoT + harness contract).

    Opt-in: MAILBUS_SYNC_LAYERS=1 restores legacy patch/sync-team-pack behavior.
    """
    if os.environ.get("MAILBUS_SYNC_LAYERS", "0") != "1":
        if log:
            log("Skip full skill sync (set MAILBUS_SYNC_LAYERS=1 to enable legacy sync)")
        return
    paths = mailbus_paths()
    root = paths["root"]
    data = paths["data_dir"]
    team_pack = paths["team_pack_root"]
    patch = os.path.join(root, "tools", "patch-skills-index-framework.py")
    if os.path.isfile(patch):
        run(["python3", patch, "--data-dir", data], timeout=300)
    sync_pack = os.path.join(team_pack, "tools", "sync-team-pack.py")
    sync_all = os.path.join(root, "tools", "sync-all-agent-layers.py")
    if os.path.isfile(sync_pack):
        run(["python3", sync_pack, "--data-dir", data, "--skip-codex", "--skip-claude"], timeout=600)
    elif os.path.isfile(sync_all):
        run(["python3", sync_all, "--data-dir", data, "--skip-codex", "--skip-claude"], timeout=600)


START_TEAM_LOCK = "/tmp/start-team.lock"
_START_TEAM_PGREP = r"python3.*mailbus\.py start|start-team\.sh"


def _start_team_process_running() -> bool:
    """是否有其它 start-team / mailbus start 进程在跑。"""
    r = run(["pgrep", "-f", _START_TEAM_PGREP], timeout=10)
    if r.returncode != 0 or not (r.stdout or "").strip():
        return False
    my_pid = os.getpid()
    for token in r.stdout.split():
        with contextlib.suppress(ValueError):
            if int(token) != my_pid:
                return True
    return False


def _handle_start_team_lock_contention(log: LogFn, paths: dict[str, str]) -> int:
    """锁被占用：已就绪则轻量刷新；无持有者则清锁重试；否则等待或报错。"""
    port = paths["api_port"]
    api_url = _api_base(port) + "/"

    if probe_http(api_url):
        log("start-team lock held but mailbus healthy — lightweight refresh")
        restart_watchdog(log)
        fix_portproxy(log)
        print(f"[start-team] mailbus 已在运行 (:{port})，已刷新 watchdog/portproxy")
        return 0

    if not _start_team_process_running():
        log("Stale start-team lock (no holder process) — removing lock and retrying once")
        with contextlib.suppress(OSError):
            os.remove(START_TEAM_LOCK)
        try:
            return _start_team_locked(log, paths)
        except TimeoutError:
            pass

    if _start_team_process_running():
        log("Another start-team is running — waiting up to 60s...")
        print("[start-team] 检测到启动任务进行中，等待完成...")
        for _ in range(12):
            time.sleep(5)
            if probe_http(api_url):
                restart_watchdog(log)
                fix_portproxy(log)
                print(f"[start-team] 等待后 mailbus 已就绪 (:{port})")
                return 0
        log("Another start-team still running after 60s")
        print("[start-team] 启动任务仍在运行，请稍后再试")
        print(f"          若卡住: wsl -d Ubuntu -e rm -f {START_TEAM_LOCK}")
        return 2

    log("Lock contention without running process")
    print(f"[ERROR] start-team 锁异常，请执行: wsl -d Ubuntu -e rm -f {START_TEAM_LOCK}")
    return 1


def start_team(*, skip_lock: bool = False, fast: bool = False) -> int:
    """全量启动（原 start-team.sh）。

    fast=True：跳过 smoke、缩短/跳过部分后置（适合日常热启动）。
    """
    load_mailbus_env()
    if fast:
        os.environ["MAILBUS_START_FAST"] = "1"
    paths = mailbus_paths()
    log = default_log("start-team", "/tmp/start-team.log")
    log(f"=== start-team {time.strftime('%Y-%m-%d %H:%M:%S')} fast={int(bool(fast) or os.environ.get('MAILBUS_START_FAST') == '1')} ===")

    if not skip_lock:
        try:
            return _start_team_locked(log, paths)
        except TimeoutError:
            log("Another start-team is running — handling lock contention")
            return _handle_start_team_lock_contention(log, paths)
    return _start_team_body(log, paths)


def _start_team_locked(log: LogFn, paths: dict[str, str]) -> int:
    with flock_lock(START_TEAM_LOCK):
        return _start_team_body(log, paths)


def _ensure_team_pack(log: LogFn, paths: dict[str, str]) -> None:
    """确保 team-pack/rules、team-pack/skills 存在，供 compose 挂载。

    本地已用 symlink 指向 Vault（或目录已存在）时跳过；否则从
    ``examples/team-pack`` seed 一份 example，保证新克隆者开箱能启动。
    """
    root = Path(paths["root"])
    tp = root / "team-pack"
    examples = root / "examples" / "team-pack"
    for sub in ("rules", "skills"):
        target = tp / sub
        if target.exists() or target.is_symlink():
            continue
        src = examples / sub
        try:
            if src.is_dir():
                shutil.copytree(src, target)
                log(f"Seeded team-pack/{sub} from examples/team-pack/{sub}")
            else:
                target.mkdir(parents=True, exist_ok=True)
                log(f"Created empty team-pack/{sub} (no examples found)")
        except OSError as exc:
            log(f"WARNING: seed team-pack/{sub} failed: {exc}")


def _start_team_body(log: LogFn, paths: dict[str, str]) -> int:
        log("Waiting for Docker daemon...")
        if not ensure_docker(90, log):
            log("ERROR: Docker not running after 90s")
            print("[ERROR] Docker 未就绪。请在 WSL 执行: sudo service docker start")
            return 1

        _ensure_team_pack(log, paths)

        if docker_container_running("docker-agents-mailbus-1"):
            log("Syncing team rules (pre-start, quick)...")
            try:
                docker_exec(
                    "docker-agents-mailbus-1",
                    "python3",
                    "/mailbus/tools/sync-team-rules.py",
                    "--data-dir",
                    "/mailbus/store",
                    "--quick",
                    timeout=60,
                )
            except Exception as exc:
                log(f"WARNING: pre-start rules sync skipped: {exc}")

        log("Cleaning legacy host mailbus cron...")
        uninstall_mailbus_cron(log)

        log("Stopping legacy host services that conflict with Docker...")
        ow = os.environ.get("OPENCLAW_WATCHDOG_SCRIPT", str(Path(paths["root"]).parent / "openclaw-watchdog.py"))
        kill_process_pattern(ow)
        port = paths["api_port"]
        kill_host_port(int(port), log)
        time.sleep(1)
        kill_host_port(18789, log)
        kill_host_port(18790, log)
        time.sleep(1)

        proxy_state = os.path.join(paths["compose_dir"], ".proxy-state")
        old_proxy = ""
        if os.path.isfile(proxy_state):
            with open(proxy_state, encoding="utf-8") as fh:
                old_proxy = fh.read().strip()

        log("Syncing L0-L2 agent layer skills + Claude context (host)...")
        _sync_layers(log)

        from lib.adapters.plane.platform_runner import detect_platform

        plat = detect_platform()
        if plat == "win32":
            log("Ensuring Windows host Ollama (internal LLM)...")
            _ensure_windows_ollama(log)
            log("Starting WSL Ollama proxy (Docker → Windows host)...")
            ensure_ollama_wsl_proxy("start", log)
        elif plat == "wsl":
            log("Ensuring Ollama via ensure-ollama.py (WSL)...")
            _ensure_windows_ollama(log)
            log("Starting WSL Ollama proxy...")
            ensure_ollama_wsl_proxy("start", log)
        else:
            log(f"Skip Windows/WSL Ollama glue on {plat} — use host Ollama or MAILBUS_OLLAMA_URL")

        log("Configuring container proxy (Clash on/off)...")
        new_proxy = setup_container_proxy(log)

        log("Pre-generating browser credentials (ttyd -c / Hermes session token)...")
        try:
            from lib.adapters.config.browser_auth import ensure_all_browser_credentials
            from lib.adapters.runtime.cred_delivery import sync_browser_credentials_to_env

            creds = ensure_all_browser_credentials(paths["data_dir"])
            log(f"Browser credentials ensured: {creds or 'none (no browser agents)'}")
            synced = sync_browser_credentials_to_env(paths["data_dir"])
            if synced:
                log(f"CredDelivery synced env keys: {sorted(synced.keys())}")
        except Exception as exc:
            log(f"WARNING: pre-generate browser credentials skipped: {exc}")

        log(f"Ensuring Docker containers are up (project={paths['compose_project']})...")
        compose_dir = paths["compose_dir"]
        up = compose_cmd("up", "-d", "--remove-orphans")
        if run_stream(up, cwd=compose_dir, timeout=600) != 0:
            log("First start failed, trying rebuild...")
            run_stream(compose_cmd("up", "-d", "--build", "--remove-orphans"), cwd=compose_dir, timeout=900)

        hermes_code = run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "3", "http://127.0.0.1:9126/"],
            timeout=10,
        ).stdout.strip()
        if hermes_code != "200":
            log("Hermes :9126 not responding — ensure dashboards...")
            run_legacy_bash("ensure-hermes-dashboards.sh", log=log)
            if run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "3", "http://127.0.0.1:9126/"],
                timeout=10,
            ).stdout.strip() != "200":
                log("Hermes :9126 still down — rebuild/recreate hermes...")
                run_stream(compose_cmd("build", "hermes"), cwd=compose_dir, timeout=600)
                run_stream(compose_cmd("up", "-d", "--force-recreate", "hermes"), cwd=compose_dir, timeout=300)
                time.sleep(8)
                run_legacy_bash("ensure-hermes-dashboards.sh", log=log)
        else:
            run_legacy_bash("ensure-hermes-dashboards.sh", log=log)

        if new_proxy != old_proxy:
            log(f"Proxy changed [{old_proxy}] -> [{new_proxy}], recreating proxy-sensitive containers...")
            run_stream(
                compose_cmd("up", "-d", "--force-recreate", *_proxy_sensitive_services(paths["data_dir"])),
                cwd=compose_dir,
                timeout=600,
            )
        else:
            log("Proxy unchanged, skip force-recreate")

        log("Waiting for mailbus/Hermes to become ready...")
        ready = False
        # 用 /api/status：不依赖 docs 静态页（Vault junction 在容器内可能不可读）
        status_url = _api_base() + "/api/status"
        for _ in range(24):
            if probe_http(status_url):
                ready = True
                break
            time.sleep(5)
        if not ready:
            log(f"WARNING: mailbus :{port} not ready after 120s")
        else:
            log(f"mailbus :{port} ready")
            log("Syncing team rules (post-start, quick)...")
            try:
                docker_exec(
                    "docker-agents-mailbus-1",
                    "python3",
                    "/mailbus/tools/sync-team-rules.py",
                    "--data-dir",
                    "/mailbus/store",
                    "--quick",
                    timeout=60,
                )
            except Exception as exc:
                log(f"WARNING: post-start rules sync skipped: {exc}")
            if os.environ.get("MAILBUS_START_FAST") == "1":
                log("FAST mode — skip internal LLM / RAG bootstrap")
            else:
                log("Probing internal LLM + RAG bootstrap...")
                try:
                    docker_exec(
                        "docker-agents-mailbus-1",
                        "python3",
                        "/mailbus/tools/ops/setup-internal-llm.py",
                        "--data-dir",
                        "/mailbus/store",
                        "--rebuild-rag-if-empty",
                        "--json",
                        timeout=300,
                    )
                except Exception as exc:
                    log(f"WARNING: internal LLM setup skipped: {exc}")

        log("Waiting for AgentMemory HTTP...")
        am_ready = False
        try:
            from lib.adapters.ops.service_registry import service_url

            # Host-side wait: published localhost port (windows/wsl profile)
            am_health = service_url("agentmemory", runtime="windows").rstrip("/") + "/agentmemory/health"
        except Exception:
            am_health = "http://127.0.0.1:3111/agentmemory/health"
        for _ in range(45):
            if probe_http(am_health):
                am_ready = True
                break
            time.sleep(1)
        log("AgentMemory ready" if am_ready else "WARNING: AgentMemory not ready after 45s")

        log("Bootstrapping Codex Web UI (codex agents)...")
        run_legacy_bash("apply-codex-ui.sh", log=log)

        log("Fixing OpenClaw gateways...")
        oc_rc = run_legacy_bash("fix-openclaw-gateways.sh", log=log)
        if oc_rc != 0:
            log("WARNING: OpenClaw gateways not healthy after fix")

        log("Starting Claude Code agents (ttyd)...")
        run_legacy_bash("ensure-claude-agents.sh", paths["data_dir"], "/tmp/start-team.log", log=log)

        log("Starting mailbus CLI watchdog...")
        restart_watchdog(log)

        log("Refreshing Windows localhost port forwarding (no-op on Linux)...")
        fix_portproxy(log)

        fast = os.environ.get("MAILBUS_START_FAST") == "1" or os.environ.get("SKIP_SMOKE") == "1"
        smoke_rc = 0
        if fast:
            log("FAST mode — skip smoke test")
        else:
            log("Running smoke test...")
            smoke_rc = run_legacy_bash("smoke-test.sh", log=log)
            if smoke_rc == 0:
                log("Smoke test passed")
            else:
                log("WARNING: smoke test failed — see /tmp/start-team.log")

        print()
        run_stream(compose_cmd("ps", "--format", "table {{.Name}}\t{{.Status}}"), cwd=compose_dir)
        # OpenClaw 挂了仍只返回 mailbus OK 会让桌面脚本误报成功
        if oc_rc != 0:
            log("ERROR: OpenClaw :18789/:18790 not ready — desktop chat links will fail")
            return 1
        if smoke_rc != 0:
            return 1
        return 0


def stop_team() -> int:
    """停止团队（原 stop-team.sh）。"""
    paths = mailbus_paths()
    log = default_log("stop-team", "/tmp/stop-team.log")

    if run(["systemctl", "is-enabled", "mailbus-watchdog"], timeout=10).returncode == 0:
        run(["sudo", "systemctl", "stop", "mailbus-watchdog"], timeout=30)
    else:
        kill_process_pattern(os.path.join(paths["compose_dir"], "mailbus-launch-watchdog.sh"))
    time.sleep(1)

    stop_claude_agents(log)
    ensure_ollama_wsl_proxy("stop", log)
    rc = run_stream(compose_cmd("down"), cwd=paths["compose_dir"], timeout=300)
    print("All containers stopped")
    return rc


def wsl_recover(*, full: bool = False, scan: bool = True) -> int:
    """WSL 轻量恢复（原 wsl-recover.sh）。"""
    paths = mailbus_paths()
    log = default_log("wsl-recover", "/tmp/wsl-recover.log")
    log("=== wsl-recover start ===")
    port = paths["api_port"]

    if full:
        log("FULL=1 → start_team()")
        return start_team()

    if probe_http(_api_base(port) + "/"):
        log("mailbus OK in WSL — refresh portproxy + watchdog only")
        restart_watchdog(log)
        fix_portproxy(log)
        curl = win_curl_exe()
        if curl:
            code = run(
                [curl, "-s", "-o", os.devnull, "-w", "%{http_code}", "--connect-timeout", "5", f"http://localhost:{port}/"],
                timeout=15,
            ).stdout.strip().replace("\r", "")
            if code == "200":
                log("Windows localhost OK — done (fast path)")
                return 0
        log("WARN: WSL OK but Windows localhost still down")
        return 2

    if not ensure_docker(60, log):
        log("ERROR: Docker not ready after 60s")
        return 1

    log("Starting core stack (mailbus + hermes)...")
    compose_dir = paths["compose_dir"]
    if run_stream(compose_cmd("up", "-d", "mailbus", "hermes"), cwd=compose_dir) != 0:
        log("compose up failed — retry with build")
        if run_stream(compose_cmd("up", "-d", "--build", "mailbus", "hermes"), cwd=compose_dir) != 0:
            return 1

    log("Ollama WSL proxy...")
    ensure_ollama_wsl_proxy("start", log)

    log("Waiting for mailbus...")
    ready = False
    status_url = _api_base(port) + "/api/status"
    for _ in range(24):
        if probe_http(status_url):
            ready = True
            break
        time.sleep(5)
    if not ready:
        log(f"ERROR: mailbus :{port} not ready after 120s")
        run_stream(compose_cmd("ps"), cwd=compose_dir)
        return 1
    log("mailbus ready")

    log("Restart launch watchdog...")
    restart_watchdog(log)

    fix_portproxy(log)

    if scan and docker_container_running("docker-agents-mailbus-1"):
        log("Triggering one scan...")
        docker_exec(
            "docker-agents-mailbus-1",
            "python3",
            "-m",
            "bus",
            "scan",
            "--data-dir",
            "/mailbus/store",
            timeout=120,
        )

    log("=== wsl-recover done ===")
    run_stream(compose_cmd("ps", "--format", "table {{.Name}}\t{{.Status}}"), cwd=compose_dir)
    return 0


def start_from_windows(*, open_browser: bool = False, fast: bool = False) -> int:
    """Windows 入口：唤醒 WSL → Python start → portproxy → 可选开浏览器。"""
    from .platform_runner import open_windows_urls

    paths = mailbus_paths()
    port = paths["api_port"]
    print("==========================================")
    print("  mailbus - Docker Agent Starter")
    if fast:
        print("  mode: FAST (skip smoke)")
    print("==========================================")

    if not wsl_exe():
        print("[ERROR] wsl not found")
        return 1

    print("[0/4] Wake WSL Ubuntu...")
    if not wake_wsl():
        print("[ERROR] Cannot start WSL Ubuntu")
        return 1
    print("      WSL OK")

    if not fast:
        print("[0.5/4] Ensure Ollama (local internal LLM)...")
        _ensure_windows_ollama()
    else:
        print("[0.5/4] FAST — skip Ollama ensure")

    print("[1/4] Start Docker containers via mailbus.py start ...")
    start_args = ["start"]
    if fast:
        start_args.append("--fast")
    inner = mailbus_py_in_wsl(start_args)
    rc = run_wsl(inner, timeout=3600)
    if rc != 0:
        print("[ERROR] mailbus start failed")
        print("        Log: wsl -d Ubuntu -e tail -50 /tmp/start-team.log")
        return rc

    print("[2/4] Fix Windows localhost port forwarding...")
    fix_portproxy()

    print("[3/4] Check mailbus...")
    status_url = f"http://127.0.0.1:{port}/api/status"
    win_ok = probe_http(status_url, timeout=8)
    if not win_ok:
        print(f"      localhost:{port}/api/status 不可达，再次尝试 portproxy...")
        fix_portproxy()
        win_ok = probe_http(status_url, timeout=8)

    if win_ok:
        print(f"      OK  http://localhost:{port}/  (api/status)")
    else:
        print(f"[ERROR] mailbus 未就绪 (localhost:{port}/api/status)")
        print("        1) 双击桌面 Fix-Mailbus-Port.bat（UAC 点「是」）")
        print("        2) 查看日志: wsl -d Ubuntu -e tail -50 /tmp/start-team.log")
        print("        3) 诊断: python tools/mailbus.py doctor")
        print("        4) recover: python tools/mailbus.py recover health")
        return 1

    # 桌面常用入口：OpenClaw gateway；mailbus 好但 gateway 挂了时必须明示
    oc_ok = probe_http("http://127.0.0.1:18789/", timeout=5, ok_codes=frozenset({200, 401, 403, 404}))
    if not oc_ok:
        print("[WARN] OpenClaw gateway :18789 未就绪（聊天页会打不开）")
        print("       修复: python tools/mailbus.py openclaw fix")
        print("       日志: wsl -d Ubuntu -e docker exec docker-agents-openclaw-1 tail -40 /tmp/openclaw-gw-18789.log")

    print("==========================================")
    print(f"  mailbus:  http://localhost:{port}/")
    print("  Hermes:  9120-9122,9125-9127")
    print("  OpenClaw: 18789 agent-m", "OK" if oc_ok else "FAIL", ", 18790 agent-l")
    print("  Codex:   9240 agent-g, 9241 agent-e")
    print("  Claude:  9260 agent-h, 9261 agent-f")
    print("==========================================")

    if open_browser and win_ok:
        from lib.adapters.runtime.cred_delivery import resolve_openclaw_token, sync_browser_credentials_to_env

        sync_browser_credentials_to_env(paths.get("data_dir") or os.environ.get("MAILBUS_DATA") or "store")
        token = resolve_openclaw_token(paths.get("data_dir") or "store") or os.environ.get(
            "OPENCLAW_GATEWAY_TOKEN", "change-me"
        )
        open_windows_urls(
            [
                f"http://localhost:{port}/",
                "http://localhost:9120/chat",
                f"http://localhost:18789/chat?token={token}",
                f"http://localhost:18790/chat?token={token}",
                "http://localhost:9240/",
                "http://localhost:9260/",
                "http://localhost:9261/",
            ]
        )
    return 0


def stop_from_windows() -> int:
    if not wsl_exe():
        print("[ERROR] wsl not found")
        return 1
    return run_wsl(mailbus_py_in_wsl(["stop"]), timeout=600)
