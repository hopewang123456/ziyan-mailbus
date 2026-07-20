"""start-team 后置步骤 — Python 版（原 apply-codex-ui / fix-openclaw / ensure-claude / smoke 等）。"""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import time
from datetime import datetime

from .claude_browser_launch import ensure_claude_web
from .env_bootstrap import mailbus_paths
from .platform_runner import (
    LogFn,
    compose_cmd,
    detect_platform,
    docker_container_running,
    docker_exec,
    probe_http,
    run,
    run_powershell_file,
    run_stream,
    win_curl_exe,
)

OK_HTTP = frozenset({200, 301, 302, 401, 404})
CODEX_BIN_SCRIPTS = (
    "start-codex-ui.sh",
    "start-codex-web.sh",
    "ensure-codex-browser.sh",
    "render-codex-config.sh",
    "sync-codex-home-mirror.sh",
    "pin-codex-workspace.sh",
    "wait-agentmemory.sh",
)
MAILBUS_CRON_RE = re.compile(
    r"python3 -m bus (scan|serve)|bus\.py (scan|serve)|mailbus-memory-bridge|"
    r"mailbox-daemon|daemon-manager|api-health\.sh|mailbus-patrol-cron|"
    r"cron-lingxun-patrol|mailbus-daily-report|cron-start-mailbus|mailbus-boot|"
    r"mailbus-review-cron|/ai_tools/mail/logs.*-mtime|find /mnt/e/ai_tools/mail/logs"
)
MAILBUS_CRON_COMMENT_RE = re.compile(
    r"^#.*(mailbus|Mailbox Daemon|mailbox-daemon|memory-bridge|api-health|"
    r"mailbus-boot|清理旧日志|mail/logs)"
)


def _log_line(log: LogFn | None, msg: str) -> None:
    if log:
        log(msg)
    else:
        print(msg)


def uninstall_mailbus_cron(log: LogFn | None = None) -> int:
    """移除 WSL 宿主机 mailbus 相关 crontab。"""
    if detect_platform() not in ("linux", "wsl"):
        _log_line(log, "[uninstall-cron] skip (not Linux/WSL)")
        return 0
    r = run(["crontab", "-l"], timeout=15)
    lines = (r.stdout or "").splitlines() if r.returncode == 0 else []
    if not lines:
        _log_line(log, "[uninstall-cron] 无需清理（空 crontab）")
        return 0
    kept = [
        ln
        for ln in lines
        if not MAILBUS_CRON_RE.search(ln) and not MAILBUS_CRON_COMMENT_RE.search(ln)
    ]
    if len(kept) == len(lines):
        _log_line(log, "[uninstall-cron] 无需清理（无 mailbus WSL cron 条目）")
        return 0
    if kept:
        proc = subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n", text=True, timeout=15)
        _log_line(log, "[uninstall-cron] 已移除 mailbus 相关 WSL cron，保留其它条目")
        return proc.returncode
    run(["crontab", "-r"], timeout=15)
    _log_line(log, "[uninstall-cron] 已清空 crontab（仅剩 mailbus 条目）")
    return 0


def apply_codex_ui(log: LogFn | None = None) -> int:
    """热更新灵霄/灵鉴 Codex Web UI（原 apply-codex-ui.sh）。"""
    paths = mailbus_paths()
    compose_dir = paths["compose_dir"]
    project = paths["compose_project"]
    agent_dir = os.path.join(compose_dir, "codex-agent")
    root = paths["root"]

    _log_line(log, "=== recreate with new port mappings ===")
    run_stream(
        compose_cmd("up", "-d", "--force-recreate", "--no-build", "lingxiao", "lingjian"),
        cwd=compose_dir,
        timeout=600,
    )
    _log_line(log, "=== wait startup ===")
    time.sleep(15)

    for name in ("lingxiao", "lingjian"):
        ctr = f"{project}-{name}-1"
        _log_line(log, f"=== inject scripts + start services in {ctr} ===")
        for script in CODEX_BIN_SCRIPTS:
            src = os.path.join(agent_dir, script)
            if not os.path.isfile(src):
                continue
            run(["docker", "cp", src, f"{ctr}:/usr/local/bin/{script}"], timeout=60)
            docker_exec(ctr, "chmod", "+x", f"/usr/local/bin/{script}", timeout=30)
        for src, dst in (
            (os.path.join(agent_dir, "entrypoint.sh"), "/entrypoint.sh"),
            (os.path.join(agent_dir, "codex-ui-proxy.mjs"), "/usr/local/share/codex/codex-ui-proxy.mjs"),
        ):
            if os.path.isfile(src):
                run(["docker", "cp", src, f"{ctr}:{dst}"], timeout=60)
                if dst.endswith(".sh"):
                    docker_exec(ctr, "chmod", "+x", dst, timeout=30)
        docker_exec(ctr, "ensure-codex-browser.sh", timeout=180)

    time.sleep(8)
    run(["docker", "ps", "--format", "table {{.Names}}\t{{.Ports}}"], timeout=30)

    smoke_py = os.path.join(root, "tools", "smoke-codex-agent.py")
    if os.path.isfile(smoke_py):
        _log_line(log, "=== smoke ===")
        for ctr in (f"{project}-lingxiao-1", f"{project}-lingjian-1"):
            run(["python3", smoke_py, "--container", ctr], timeout=120)
    _log_line(log, "=== DONE ===")
    return 0


def fix_openclaw_gateways(log: LogFn | None = None) -> int:
    """修复小七/一哥 OpenClaw gateway（原 fix-openclaw-gateways.sh）。"""
    paths = mailbus_paths()
    container = f"{paths['compose_project']}-openclaw-1"
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "ziyan-team")

    names = run(["docker", "ps", "--format", "{{.Names}}"], timeout=15).stdout or ""
    if container not in names.split():
        _log_line(log, f"[fix-openclaw] container {container} not running — skip")
        return 0

    _log_line(log, f"[fix-openclaw] resetting device pairing + restarting gateways in {container} ...")
    inner_script = f"""
set -euo pipefail
for profile in xiaoqi yige; do
  rm -rf "/workspace/data/.openclaw-${{profile}}/devices" \\
         "/workspace/data/.openclaw-${{profile}}/identity" 2>/dev/null || true
done
bash /init-openclaw-profiles.sh
pkill -x openclaw 2>/dev/null || true
sleep 2
TOKEN={token!r}
start_one() {{
  local name="$1" port="$2"
  local statedir="/workspace/data/.openclaw-${{name}}"
  local extra=()
  [ "$name" = "yige" ] && extra=("OPENCLAW_ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS=1")
  rm -rf "${{statedir}}/devices" "${{statedir}}/identity" 2>/dev/null || true
  nohup env "${{extra[@]}}" \\
    OPENCLAW_STATE_DIR="$statedir" \\
    OPENCLAW_CONFIG_PATH="${{statedir}}/openclaw.json" \\
    DEEPSEEK_API_KEY="${{DEEPSEEK_API_KEY:-}}" \\
    OPENAI_API_KEY="${{OPENAI_API_KEY:-}}" \\
    GLM_API_KEY="${{GLM_API_KEY:-}}" \\
    ZHIPU_API_KEY="${{ZHIPU_API_KEY:-}}" \\
    DASHSCOPE_API_KEY="${{DASHSCOPE_API_KEY:-}}" \\
    QWEN_API_KEY="${{QWEN_API_KEY:-}}" \\
    ALIBABA_API_KEY="${{ALIBABA_API_KEY:-}}" \\
    HTTP_PROXY="${{HTTP_PROXY:-}}" \\
    HTTPS_PROXY="${{HTTPS_PROXY:-}}" \\
    NO_PROXY="${{NO_PROXY:-localhost,127.0.0.1,::1,iii-engine,agentmemory,mailbus,172.28.0.0/16,host.docker.internal}}" \\
    OPENCLAW_GATEWAY_TOKEN="$TOKEN" \\
    openclaw gateway run --allow-unconfigured \\
      --auth token --token "$TOKEN" \\
      --port "$port" --bind auto --force \\
    >"/tmp/openclaw-gw-${{port}}.log" 2>&1 &
  echo "  ${{name}} (${{port}}) restarted"
}}
start_one xiaoqi 18789
start_one yige 18790
"""
    run(["docker", "exec", container, "bash", "-lc", inner_script], timeout=300)

    for port in (18789, 18790):
        ok = False
        for _ in range(25):
            if probe_http(f"http://127.0.0.1:{port}/", ok_codes=frozenset({200, 401, 403, 404})):
                ok = True
                break
            time.sleep(1)
        _log_line(log, f"[fix-openclaw] :{port} -> {'OK' if ok else 'FAIL'}")

    _log_line(log, f"[fix-openclaw] 小七: http://localhost:18789/chat?token={token}")
    _log_line(log, f"[fix-openclaw] 一哥: http://localhost:18790/chat?token={token}")
    return 0


def ensure_claude_agents(data_dir: str | None = None, log: LogFn | None = None) -> int:
    """启动灵云/灵验 Claude ttyd（原 ensure-claude-agents.sh）。"""
    paths = mailbus_paths()
    data = data_dir or paths["data_dir"]
    _log_line(log, "[ensure-claude] Starting Claude Code web terminals...")

    am_url = os.environ.get("AGENTMEMORY_URL", "http://127.0.0.1:3111")
    if probe_http(f"{am_url}/agentmemory/health"):
        _log_line(log, f"[ensure-claude] AgentMemory healthy at {am_url}")
    else:
        _log_line(log, f"[ensure-claude] WARNING: AgentMemory unreachable at {am_url}")

    sync_py = os.path.join(paths["root"], "tools", "sync-claude-agent-context.py")
    if os.path.isfile(sync_py):
        for agent in ("lingyun", "lingyan"):
            run(["python3", sync_py, agent, "--data-dir", data], timeout=120)

    rc = 0
    for agent, port in (("lingyun", 9260), ("lingyan", 9261)):
        try:
            ensure_claude_web(agent, data, wait_seconds=15)
            _log_line(log, f"[ensure-claude] OK {agent} ttyd :{port}")
        except Exception as exc:
            _log_line(log, f"[ensure-claude] WARNING: {agent} ttyd :{port} failed: {exc}")
            rc = 1
    return rc


def stop_claude_agents(log: LogFn | None = None) -> int:
    """停止灵云/灵验 Claude ttyd（原 stop-claude-agents.sh）。"""
    if detect_platform() not in ("linux", "wsl"):
        return 0
    log_dir = "/tmp/claude-web"
    for agent in ("lingyun", "lingyan"):
        pid_file = os.path.join(log_dir, f"ttyd-{agent}.pid")
        if os.path.isfile(pid_file):
            try:
                with open(pid_file, encoding="utf-8") as fh:
                    pid = int(fh.read().strip())
                os.kill(pid, signal.SIGTERM)
            except (OSError, ValueError):
                pass
            with contextlib.suppress(OSError):
                os.remove(pid_file)
        run(["tmux", "kill-session", "-t", f"claude-{agent}"], timeout=10)
    run(["fuser", "-k", "9260/tcp", "9261/tcp"], timeout=10)
    _log_line(log, "[stop-claude] Claude ttyd sessions stopped")
    return 0


def _check_http(name: str, url: str, *, pass_fail: list[int]) -> bool:
    for _ in range(6):
        code = "000"
        try:
            import urllib.request

            with urllib.request.urlopen(url, timeout=5) as resp:
                code = str(resp.status)
        except Exception:
            r = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "5", url], timeout=10)
            code = (r.stdout or "000").strip()
        if code in {str(c) for c in OK_HTTP}:
            print(f"OK  {name}  {url}  ({code})")
            pass_fail[0] += 1
            return True
        time.sleep(5)
    print(f"FAIL {name}  {url}  ({code})")
    pass_fail[1] += 1
    return False


def smoke_test(*, wait_sec: int | None = None, am_persist: bool = False) -> int:
    """启动后自检（原 smoke-test.sh）。"""
    paths = mailbus_paths()
    port = paths["api_port"]
    wait = int(wait_sec if wait_sec is not None else os.environ.get("SMOKE_WAIT_SEC", "20"))
    passed = [0, 0]

    print(f"=== smoke test {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    print(f"waiting {wait}s for services...")
    time.sleep(wait)

    checks = [
        ("mailbus", f"http://127.0.0.1:{port}/api/status"),
        ("lingzhao-9120", "http://127.0.0.1:9120/"),
        ("lingjin-9121", "http://127.0.0.1:9121/"),
        ("lingxi-9122", "http://127.0.0.1:9122/"),
        ("lingtuo-9126", "http://127.0.0.1:9126/"),
        ("lingxun-9125", "http://127.0.0.1:9125/"),
        ("lingzhang-9127", "http://127.0.0.1:9127/"),
        ("openclaw-xiaoqi", "http://127.0.0.1:18789/"),
        ("openclaw-yige", "http://127.0.0.1:18790/"),
        ("iii-engine", "http://127.0.0.1:3111/"),
        ("agentmemory", "http://127.0.0.1:3111/agentmemory/health"),
        ("codex-lingxiao", "http://127.0.0.1:9240/"),
        ("codex-lingjian", "http://127.0.0.1:9241/"),
        ("codex-lingxiao-ttyd", "http://127.0.0.1:9250/"),
        ("codex-lingjian-ttyd", "http://127.0.0.1:9251/"),
        ("claude-lingyun", "http://127.0.0.1:9260/"),
        ("claude-lingyan", "http://127.0.0.1:9261/"),
    ]
    for name, url in checks:
        _check_http(name, url, pass_fail=passed)

    curl = win_curl_exe()
    if curl:
        r = run(
            [curl, "-s", "-o", os.devnull, "-w", "%{http_code}", "--connect-timeout", "8", f"http://localhost:{port}/api/status"],
            timeout=15,
        )
        code = (r.stdout or "").strip().replace("\r", "")
        if code == "200":
            print(f"OK  windows-localhost-api  http://localhost:{port}/  ({code})")
            passed[0] += 1
        else:
            print(f"FAIL windows-localhost-api  http://localhost:{port}/  ({code})")
            passed[1] += 1

    print("--- Hermes API ---")
    if not docker_container_running("docker-agents-hermes-1"):
        print("WARN hermes container not running — skip API checks")
    else:
        proxy = docker_exec("docker-agents-hermes-1", "printenv", "HTTP_PROXY", timeout=15).stdout.strip()
        print(f"HTTP_PROXY={proxy or '<empty>'}")
        ds = docker_exec(
            "docker-agents-hermes-1",
            "curl",
            "-s",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "--connect-timeout",
            "15",
            "https://api.deepseek.com/v1/models",
            timeout=30,
        ).stdout.strip()
        if ds in ("401", "200"):
            print(f"OK  deepseek-api ({ds})")
            passed[0] += 1
        else:
            print(f"FAIL deepseek-api ({ds})")
            passed[1] += 1

        print("--- Hermes chat (lingzhao) ---")
        chat = docker_exec(
            "docker-agents-hermes-1",
            "hermes",
            "chat",
            "-Q",
            "-q",
            "回复一个字：好",
            "--profile",
            "lingzhao",
            timeout=120,
        )
        chat_out = (chat.stdout or "") + (chat.stderr or "")
        if "session_id:" in chat_out:
            print("OK  hermes-chat lingzhao")
            passed[0] += 1
        else:
            print("FAIL hermes-chat lingzhao")
            for line in chat_out.splitlines()[-5:]:
                print(line)
            passed[1] += 1

    print("--- Internal LLM health ---")
    if docker_container_running("docker-agents-mailbus-1"):
        llm = docker_exec(
            "docker-agents-mailbus-1",
            "python3",
            "/mailbus/tools/ops/setup-internal-llm.py",
            "--data-dir",
            "/mailbus/store",
            "--json",
            timeout=120,
        )
        llm_out = llm.stdout or "{}"
        if '"ready": true' in llm_out or '"active_provider": "local"' in llm_out:
            print("OK  internal-llm ready/local")
            passed[0] += 1
        else:
            print("WARN internal-llm not ready (remote fallback may be needed)")
            print("\n".join(llm_out.splitlines()[:5]))
    else:
        print("WARN mailbus container not running — skip internal LLM check")

    if am_persist or os.environ.get("SMOKE_AM_PERSIST") == "1":
        print("--- AgentMemory persistence probe ---")
        probe = os.path.join(paths["root"], "tools", "ops", "check-agentmemory-persistence.py")
        if os.path.isfile(probe):
            r = run(["python3", probe, "--url", "http://127.0.0.1:3111"], timeout=120)
            if r.returncode == 0:
                print("OK  agentmemory-persistence")
                passed[0] += 1
            else:
                print("FAIL agentmemory-persistence")
                passed[1] += 1

    print(f"=== result: {passed[0]} passed, {passed[1]} failed ===")
    return passed[1]


def fix_portproxy(log: LogFn | None = None) -> int:
    """刷新 Windows localhost→WSL portproxy。"""
    paths = mailbus_paths()
    ps1 = paths["fix_portproxy_ps1"]
    if not os.path.isfile(ps1):
        _log_line(log, f"WARN: missing {ps1}")
        return 1
    _log_line(log, "Refresh portproxy (UAC may prompt)...")
    return run_powershell_file(ps1).returncode
