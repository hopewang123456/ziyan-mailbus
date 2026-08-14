"""start-team 后置步骤 — Python 版（原 apply-codex-ui / fix-openclaw / ensure-claude / smoke 等）。"""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import time
from datetime import datetime

from lib.infra.clock import now_dt
from lib.adapters.frameworks.claude_browser_launch import ensure_claude_web
from lib.infra.env_bootstrap import mailbus_paths
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


def _store_config(data_dir: str) -> dict:
    """读取 store/config.json（agents 名册 SoT）。"""
    from lib.infra.utils import json_read

    return json_read(os.path.join(data_dir, "config.json"), {})


def _agents_of_type(data_dir: str, *types: str) -> list:
    """按 framework/type 过滤 agents，返回 [(agent_id, cfg), ...] 有序列表。"""
    cfg = _store_config(data_dir)
    agents = cfg.get("agents") or {}
    if isinstance(agents, dict):
        items = sorted(agents.items())
    else:
        items = []
    return [(aid, rec) for aid, rec in items if (rec.get("type") or rec.get("framework") or "") in types]


def _first_agents_of_type(data_dir: str, *types: str) -> list:
    """按类型取前 N 个 agent id（无则空）。"""
    return [aid for aid, _ in _agents_of_type(data_dir, *types)]


def _smoke_agent_checks(data_dir: str) -> list:
    """smoke 检查项 — 从 store config 动态构建（agent 名/端口不硬编码）。"""
    cfg = _store_config(data_dir)
    agents = cfg.get("agents") or {}
    if not isinstance(agents, dict):
        return []
    checks: list = []
    for aid, rec in sorted(agents.items()):
        if not isinstance(rec, dict):
            continue
        fw = rec.get("type") or rec.get("framework") or ""
        if fw == "hermes_profile":
            launch = rec.get("launch") or {}
            browser = launch.get("browser") or {}
            port = browser.get("dashboard_port")
            if not port:
                docker = rec.get("docker") or {}
                port = docker.get("port")
            if port:
                checks.append((f"hermes-{aid}", f"http://127.0.0.1:{port}/"))
        elif fw == "openclaw":
            launch = rec.get("launch") or {}
            port = ((launch.get("browser") or {}).get("gateway_port")) or 18789
            checks.append((f"openclaw-{aid}", f"http://127.0.0.1:{port}/"))
        elif fw == "codex":
            launch = rec.get("launch") or {}
            browser = launch.get("browser") or {}
            web_port = browser.get("web_port")
            if web_port:
                checks.append((f"codex-{aid}", f"http://127.0.0.1:{web_port}/"))
            ttyd_url = browser.get("ttyd_url")
            if ttyd_url:
                checks.append((f"codex-{aid}-ttyd", ttyd_url))
        elif fw == "claude_code":
            launch = rec.get("launch") or {}
            browser = launch.get("browser") or {}
            url = browser.get("url")
            if url:
                port = browser.get("web_port") or browser.get("port")
                if port and "{port}" in url:
                    url = url.replace("{port}", str(port))
                checks.append((f"claude-{aid}", url))
    return checks
MAILBUS_CRON_RE = re.compile(
    r"python3 -m bus (scan|serve)|bus\.py (scan|serve)|mailbus-memory-bridge|"
    r"mailbox-daemon|daemon-manager|api-health\.sh|mailbus-patrol-cron|"
    r"cron-patrol|mailbus-daily-report|cron-start-mailbus|mailbus-boot|"
    r"mailbus-review-cron|/mail/logs.*-mtime|find /mail/logs"
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


def apply_codex_ui(data_dir: str | None = None, log: LogFn | None = None) -> int:
    """热更新 Codex Web UI（原 apply-codex-ui.sh）。"""
    paths = mailbus_paths()
    compose_dir = paths["compose_dir"]
    project = paths["compose_project"]
    agent_dir = os.path.join(compose_dir, "codex-agent")
    root = paths["root"]
    data = data_dir or paths["data_dir"]

    codex_agents = _first_agents_of_type(data, "codex")
    if not codex_agents:
        _log_line(log, "[codex-ui] no codex agents in store config — skip")
        return 0

    _log_line(log, "=== recreate with new port mappings ===")
    run_stream(
        compose_cmd("up", "-d", "--force-recreate", "--no-build", *codex_agents),
        cwd=compose_dir,
        timeout=600,
    )
    _log_line(log, "=== wait startup ===")
    time.sleep(15)

    for name in codex_agents:
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
        for name in codex_agents:
            ctr = f"{project}-{name}-1"
            run(["python3", smoke_py, "--container", ctr], timeout=120)
    _log_line(log, "=== DONE ===")
    return 0


def fix_openclaw_gateways(data_dir: str | None = None, log: LogFn | None = None) -> int:
    """修复 OpenClaw gateway（原 fix-openclaw-gateways.sh）。

    2026.7+ 常见坑：
    - 双 gateway 同时抢 startup-migration lease（sqlite state_leases）
    - 缺 deepseek plugin 时交互警告卡住
    - 配置了 codex 等无关插件时在 NTFS(/workspace) 上 npm rename → EACCES
    """
    paths = mailbus_paths()
    data = data_dir or paths["data_dir"]
    container = f"{paths['compose_project']}-openclaw-1"
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "change-me")
    profiles = _first_agents_of_type(data, "openclaw") or ["agent-b", "agent-c"]
    port_map = {aid: 18789 + i for i, aid in enumerate(profiles)}

    names = run(["docker", "ps", "--format", "{{.Names}}"], timeout=15).stdout or ""
    if container not in names.split():
        _log_line(log, f"[fix-openclaw] container {container} not running — skip")
        return 0

    reset_pairing = os.environ.get("RESET_OPENCLAW_PAIRING", "0") == "1"
    fix_plugins = os.environ.get("FIX_OPENCLAW_PLUGINS", "0") == "1"
    _log_line(
        log,
        f"[fix-openclaw] restarting gateways in {container}"
        f" (reset_pairing={int(reset_pairing)} fix_plugins={int(fix_plugins)}) ...",
    )
    # 预修复：清 lease / 坏 npm 代际目录；插件与 pairing 仅 opt-in
    inner_script = f"""
set -euo pipefail
export PYTHONPATH="/mailbus${{PYTHONPATH:+:$PYTHONPATH}}"
export CI=1 NO_COLOR=1
TOKEN={token!r}
RESET_OPENCLAW_PAIRING={int(reset_pairing)}
FIX_OPENCLAW_PLUGINS={int(fix_plugins)}

# 1) 停掉旧 gateway（只杀二进制名，避免误杀本 shell）
kill -9 $(pgrep -x openclaw) 2>/dev/null || true
sleep 1

# 2) 清迁移租约 + 权限/坏缓存；写 openclaw.json 插件仅 FIX_OPENCLAW_PLUGINS=1
python3 - <<'PY'
import json, os, sqlite3, shutil
from pathlib import Path

def clear_leases(db: str) -> None:
    if not os.path.isfile(db):
        return
    con = sqlite3.connect(db)
    try:
        con.execute("DELETE FROM state_leases")
        con.commit()
        print("[fix-openclaw] cleared leases", db)
    except Exception as e:
        print("[fix-openclaw] lease skip", db, e)
    finally:
        con.close()

fix_plugins = os.environ.get("FIX_OPENCLAW_PLUGINS", "0") == "1"
for profile in ({ ", ".join(repr(p) for p in profiles + [""]) }):
    base = Path("/workspace/data") / (f".openclaw-{{profile}}" if profile else ".openclaw")
    clear_leases(str(base / "state" / "openclaw.sqlite"))
    npm = base / "npm"
    if npm.is_dir():
        # NTFS 上残留的 generation 目录常导致 npm rename EACCES
        for p in npm.rglob("*"):
            pass
        for gen in npm.glob("projects/*__openclaw-generation__*"):
            print("[fix-openclaw] rm gen", gen)
            shutil.rmtree(gen, ignore_errors=True)
        os.system(f"chmod -R u+rwX {{npm}} 2>/dev/null || true")
    if not fix_plugins:
        continue
    cfg_path = base / "openclaw.json"
    if not cfg_path.is_file():
        continue
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    entries = cfg.setdefault("plugins", {{}}).setdefault("entries", {{}})
    changed = False
    for bad in ("codex", "@openclaw/codex"):
        if bad in entries:
            del entries[bad]
            changed = True
            print("[fix-openclaw]", profile or "shared", "drop plugin", bad)
    if "deepseek" not in entries:
        entries["deepseek"] = {{"enabled": True}}
        changed = True
    if changed:
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
PY

bash /init-openclaw-profiles.sh || true

start_one() {{
  local name="$1" port="$2"
  local statedir="/workspace/data/.openclaw-${{name}}"
  local extra=()
  if [ "${{RESET_OPENCLAW_PAIRING:-0}}" = "1" ]; then
    rm -rf "${{statedir}}/devices" "${{statedir}}/identity" 2>/dev/null || true
  fi
  # 确保 deepseek 插件（缺了会弹交互警告卡住）；不写 openclaw.json
  env OPENCLAW_STATE_DIR="$statedir" OPENCLAW_CONFIG_PATH="${{statedir}}/openclaw.json" \\
    openclaw --no-color plugins install @openclaw/deepseek-provider \\
    >/tmp/openclaw-plugin-${{name}}.log 2>&1 || true
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
    CI=1 NO_COLOR=1 \\
    openclaw --no-color gateway run --allow-unconfigured \\
      --auth token --token "$TOKEN" \\
      --port "$port" --bind lan --force \\
    >"/tmp/openclaw-gw-${{port}}.log" 2>&1 &
  echo "  ${{name}} (${{port}}) restarted pid=$!"
}}
_start_calls = []
for _i, _aid in enumerate(profiles):
    _port = port_map[_aid]
    if _i > 0:
        _start_calls.append("# 错开，避免抢同一个 migration lease")
        _start_calls.append("sleep 15")
    _start_calls.append(f"start_one {_aid} {_port}")
inner_script += "\n" + "\n".join(_start_calls) + "\n"""
    run(["docker", "exec", container, "bash", "-lc", inner_script], timeout=600)

    fails = 0
    for port in sorted(set(port_map.values())):
        ok = False
        for _ in range(40):
            if probe_http(f"http://127.0.0.1:{port}/", ok_codes=frozenset({200, 401, 403, 404})):
                ok = True
                break
            time.sleep(2)
        _log_line(log, f"[fix-openclaw] :{port} -> {'OK' if ok else 'FAIL'}")
        if not ok:
            fails += 1
            # 拉一点日志方便桌面启动排障
            tip = run(
                ["docker", "exec", container, "sh", "-c", f"tail -20 /tmp/openclaw-gw-{port}.log 2>/dev/null || true"],
                timeout=15,
            ).stdout.strip()
            if tip and log:
                for line in tip.splitlines()[-8:]:
                    log(f"[fix-openclaw] log:{port}: {line}")

    for aid, port in port_map.items():
        _log_line(log, f"[fix-openclaw] {aid}: http://localhost:{port}/chat?token={token}")
    return 1 if fails else 0


def ensure_claude_agents(data_dir: str | None = None, log: LogFn | None = None) -> int:
    """启动 Claude Code ttyd（原 ensure-claude-agents.sh）。"""
    paths = mailbus_paths()
    data = data_dir or paths["data_dir"]
    _log_line(log, "[ensure-claude] Starting Claude Code web terminals...")

    claude_agents = _first_agents_of_type(data, "claude_code")
    if not claude_agents:
        _log_line(log, "[ensure-claude] no claude_code agents in store config — skip")
        return 0

    try:
        from lib.adapters.ops.service_registry import service_url

        am_url = service_url("agentmemory")
    except Exception:
        am_url = os.environ.get("AGENTMEMORY_URL", "http://127.0.0.1:3111")
    if probe_http(f"{am_url}/agentmemory/health"):
        _log_line(log, f"[ensure-claude] AgentMemory healthy at {am_url}")
    else:
        _log_line(log, f"[ensure-claude] WARNING: AgentMemory unreachable at {am_url}")

    sync_py = os.path.join(paths["root"], "tools", "sync-claude-agent-context.py")
    if os.path.isfile(sync_py):
        for agent in claude_agents:
            run(["python3", sync_py, agent, "--data-dir", data], timeout=120)

    rc = 0
    for i, agent in enumerate(claude_agents):
        port = 9260 + i
        try:
            ensure_claude_web(agent, data, wait_seconds=15)
            _log_line(log, f"[ensure-claude] OK {agent} ttyd :{port}")
        except Exception as exc:
            _log_line(log, f"[ensure-claude] WARNING: {agent} ttyd :{port} failed: {exc}")
            rc = 1
    return rc


def stop_claude_agents(data_dir: str | None = None, log: LogFn | None = None) -> int:
    """停止 Claude ttyd（原 stop-claude-agents.sh）。"""
    if detect_platform() not in ("linux", "wsl"):
        return 0
    paths = mailbus_paths()
    data = data_dir or paths["data_dir"]
    log_dir = "/tmp/claude-web"
    claude_agents = _first_agents_of_type(data, "claude_code") or ["agent-a"]
    for agent in claude_agents:
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
    for port in range(9260, 9260 + max(len(claude_agents), 1)):
        run(["fuser", "-k", f"{port}/tcp"], timeout=10)
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
    data_dir = paths["data_dir"]
    wait = int(wait_sec if wait_sec is not None else os.environ.get("SMOKE_WAIT_SEC", "20"))
    passed = [0, 0]

    print(f"=== smoke test {now_dt():%Y-%m-%d %H:%M:%S} ===")
    print(f"waiting {wait}s for services...")
    time.sleep(wait)

    try:
        from lib.adapters.ops.service_registry import service_url

        am_host = service_url("agentmemory", runtime="windows").rstrip("/")
    except Exception:
        am_host = "http://127.0.0.1:3111"
    checks = [("mailbus", f"http://127.0.0.1:{port}/api/status")]
    checks.extend(_smoke_agent_checks(data_dir))
    checks.extend([
        ("iii-engine", f"{am_host}/"),
        ("agentmemory", f"{am_host}/agentmemory/health"),
    ])
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

        hermes_profile = _first_agents_of_type(data_dir, "hermes_profile")
        chat_agent = hermes_profile[0] if hermes_profile else "agent-a"
        print(f"--- Hermes chat ({chat_agent}) ---")
        chat = docker_exec(
            "docker-agents-hermes-1",
            "hermes",
            "chat",
            "-Q",
            "-q",
            "回复一个字：好",
            "--profile",
            chat_agent,
            timeout=120,
        )
        chat_out = (chat.stdout or "") + (chat.stderr or "")
        if "session_id:" in chat_out:
            print(f"OK  hermes-chat {chat_agent}")
            passed[0] += 1
        else:
            print(f"FAIL hermes-chat {chat_agent}")
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
            try:
                from lib.adapters.ops.service_registry import service_url

                am_url = service_url("agentmemory", runtime="windows")
            except Exception:
                am_url = "http://127.0.0.1:3111"
            r = run(["python3", probe, "--url", am_url], timeout=120)
            if r.returncode == 0:
                print("OK  agentmemory-persistence")
                passed[0] += 1
            else:
                print("FAIL agentmemory-persistence")
                passed[1] += 1

    print(f"=== result: {passed[0]} passed, {passed[1]} failed ===")
    return passed[1]


def fix_portproxy(log: LogFn | None = None) -> int:
    """刷新 Windows localhost→WSL portproxy。非 Windows 平台直接跳过（Linux 可原生监听）。"""
    from lib.adapters.plane.platform_runner import detect_platform

    plat = detect_platform()
    if plat in ("linux", "darwin"):
        _log_line(log, f"portproxy skipped on {plat} (native listen; no Windows portproxy)")
        return 0
    paths = mailbus_paths()
    ps1 = paths["fix_portproxy_ps1"]
    if not os.path.isfile(ps1):
        _log_line(log, f"WARN: missing {ps1}")
        return 1
    _log_line(log, "Refresh portproxy (UAC may prompt)...")
    return run_powershell_file(ps1).returncode
