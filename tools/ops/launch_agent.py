#!/usr/bin/env python3
"""统一 agent 启动 — 替代 tools/ops/launch-agent.sh。"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from lib.agent_adapters import OpenClawAdapter, resolve_container  # noqa: E402
from lib.launch_ports import resolve_port  # noqa: E402
from lib.claude_browser_launch import launch_claude_browser  # noqa: E402
from lib.claude_launch import enqueue_launch_queue, launch_claude_cli  # noqa: E402
from lib.desktop_launch import agent_has_desktop, launch_desktop  # noqa: E402
from lib.env_bootstrap import load_mailbus_env, mailbus_paths  # noqa: E402
from lib.platform_runner import (  # noqa: E402
    docker_argv,
    docker_cli_bridge_available,
    init_stdio,
    probe_http,
    run,
    running_in_mailbus_docker,
)
from lib.utils import json_read  # noqa: E402


def _config_path(data_dir: str) -> str:
    if os.path.isfile("/mailbus/store/config.json"):
        return "/mailbus/store/config.json"
    return os.path.join(os.path.abspath(data_dir), "config.json")


def _merged_launch(cfg: dict, agent_key: str, mode: str) -> dict:
    agent = (cfg.get("agents") or {}).get(agent_key) or {}
    tmpl_name = (agent.get("launch") or {}).get("template", "")
    tmpl = (cfg.get("agent_types") or {}).get("launch_templates", {}).get(tmpl_name, {})
    launch = agent.get("launch") or {}
    if mode == "browser":
        merged = dict(tmpl.get("browser") or {})
        merged.update(launch.get("browser") or {})
    elif mode == "desktop":
        merged = dict(tmpl.get("desktop") or {})
        merged.update(launch.get("desktop") or {})
    else:
        merged = dict(tmpl.get("cli") or {})
        merged.update(launch.get("cli") or {})
    merged["kind"] = merged.get("kind", "none")
    merged["_template"] = tmpl_name
    return merged


def _subst(text: str, **kwargs: str) -> str:
    out = text or ""
    for key, val in kwargs.items():
        out = out.replace("{" + key + "}", val)
    return out


def _running_in_mailbus_docker() -> bool:
    return running_in_mailbus_docker()


def _probe_urls_for_docker(url: str, *, container: str = "", internal_port: str = "") -> list[str]:
    """mailbus 容器内 localhost 端口需经 host.docker.internal 或 compose 服务名探测。"""
    urls = [url]
    if not _running_in_mailbus_docker():
        return urls
    for host in ("127.0.0.1", "localhost"):
        if host in url:
            urls.append(url.replace(host, "host.docker.internal"))
    if container and internal_port:
        scheme = "https" if url.startswith("https://") else "http"
        urls.append(f"{scheme}://{container}:{internal_port}/")
    seen: set[str] = set()
    out: list[str] = []
    for item in urls:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _probe_first(urls: list[str], *, ok_codes: frozenset[int]) -> str | None:
    for url in urls:
        if probe_http(url, ok_codes=ok_codes):
            return url
    return None


def _ensure_hermes_dashboards() -> None:
    script = os.path.join(ROOT, "docker-agents", "ensure-hermes-dashboards.sh")
    if os.path.isfile(script):
        run(["bash", script], timeout=120)


def _start_browser(url: str) -> int:
    if sys.platform == "win32":
        return run(["cmd", "/c", "start", "", url], timeout=15).returncode
    ps = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    if os.path.isfile(ps):
        return run([ps, "-NoProfile", "-Command", f"Start-Process '{url}'"], timeout=15).returncode
    cmd = "/mnt/c/Windows/System32/cmd.exe"
    if os.path.isfile(cmd):
        return run([cmd, "/c", "start", "", url], timeout=15).returncode
    print(f"[ERROR] 无法打开浏览器: {url}", file=sys.stderr)
    return 1


def _start_wsl_interactive(cmd: str, title: str) -> bool:
    if docker_cli_bridge_available() and enqueue_launch_queue(cmd, title, mode="interactive"):
        print(f"Launched {title} (cli) [docker-wsl bridge]")
        return True
    ts = int(time.time())
    script = f"/tmp/launch-window-{ts}.sh"
    body = (
        "#!/bin/bash\nset +e\n"
        f"{cmd}\n"
        'read -p "按 Enter 键关闭窗口..." _\n'
    )
    # 写入 WSL 可访问路径
    if sys.platform == "win32":
        from lib.platform_runner import wsl_exe
        from lib.utils import to_wsl_path
        import tempfile

        win_tmp = os.path.join(tempfile.gettempdir(), f"launch-window-{ts}.sh")
        with open(win_tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        script = to_wsl_path(win_tmp)
        wsl = wsl_exe()
        if not wsl:
            return False
        # start 新开窗口后立即返回，避免 subprocess 挂起
        return (
            run(
                ["cmd", "/c", "start", "\"\"", wsl, "-e", "bash", script],
                timeout=15,
            ).returncode
            == 0
        )
    with open(script, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    os.chmod(script, 0o755)
    ps = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    if os.path.isfile(ps):
        run([ps, "-Command", f"Start-Process wsl.exe -ArgumentList '-d','Ubuntu','-e','bash','{script}'"], timeout=15)
        return True
    return False


def _ensure_codex_container(agent_key: str, cfg: dict, wait_sec: int) -> str:
    agent = (cfg.get("agents") or {}).get(agent_key) or {}
    service = (agent.get("docker") or {}).get("service") or agent_key
    container = resolve_container(agent, agent_key, service)
    if container:
        names = run(docker_argv("ps", "--format", "{{.Names}}"), timeout=15).stdout or ""
        if container not in names:
            run(docker_argv("start", container), timeout=60)
            time.sleep(min(wait_sec, 5))
    return container


def _launch_browser(agent_key: str, data_dir: str, merged: dict, cfg: dict) -> int:
    kind = merged.get("kind", "none")
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "ziyan-team")

    if kind in ("codex_desktop", "codex_web", "codex_ui", "codex_docker"):
        wait_sec = int(merged.get("start_wait_seconds", 15))
        web_port = str(merged.get("web_port", ""))
        url = _subst(merged.get("url", "http://127.0.0.1:9240"), agent=agent_key, port=web_port)
        ttyd_url = _subst(merged.get("ttyd_url", ""), agent=agent_key, port=web_port)
        container = _ensure_codex_container(agent_key, cfg, wait_sec)
        ok_codes = frozenset({200, 401, 403})
        ui_candidates = _probe_urls_for_docker(url, container=container, internal_port="7681")
        ttyd_candidates = (
            _probe_urls_for_docker(ttyd_url, container=container, internal_port="7682")
            if ttyd_url
            else []
        )
        if not _probe_first(ui_candidates, ok_codes=ok_codes) and container:
            run(docker_argv("exec", container, "ensure-codex-browser.sh"), timeout=120)
            for _ in range(wait_sec):
                if _probe_first(ui_candidates, ok_codes=ok_codes):
                    break
                time.sleep(1)
        live_url = _probe_first(ui_candidates, ok_codes=ok_codes)
        if live_url:
            if not _running_in_mailbus_docker():
                _start_browser(url)
            print(f"Launched {agent_key} codex-ui {url}")
            return 0
        live_ttyd = _probe_first(ttyd_candidates, ok_codes=ok_codes)
        if live_ttyd:
            if not _running_in_mailbus_docker():
                _start_browser(ttyd_url)
            print(f"Launched {agent_key} codex-ttyd {ttyd_url}")
            return 0
        print("[ERROR] codexapp 与 ttyd 均不可用", file=sys.stderr)
        return 1

    if kind in ("claude_ttyd", "claude_web"):
        info = launch_claude_browser(agent_key, data_dir)
        url = info.get("url") or merged.get("url", "")
        if url and not os.path.isfile("/.dockerenv"):
            _start_browser(url)
        print(f"Launched {agent_key} claude-ttyd {url}")
        return 0

    if kind == "openclaw_gateway":
        port = OpenClawAdapter.resolve_gateway_port(agent_key, merged)
        url = f"http://localhost:{port}/chat?token={token}"
        if not probe_http(f"http://localhost:{port}/", ok_codes=frozenset({200, 401, 403, 404})):
            start_cmd = merged.get("start_command", "")
            if start_cmd:
                os.system(_subst(start_cmd, port=str(port), agent=agent_key))
        _start_browser(url)
        print(f"Launched {agent_key} (browser) {url}")
        return 0

    if kind == "hermes_dashboard":
        wait_sec = int(merged.get("start_wait_seconds", 15))
        agent_cfg = (cfg.get("agents") or {}).get(agent_key) or {}
        port = str(resolve_port(agent_key, agent_cfg, merged) or 9119)
        url = _subst(merged.get("url", "http://localhost:{port}/chat"), port=port, agent=agent_key)
        service = (agent_cfg.get("docker") or {}).get("service") or "hermes"
        container = resolve_container(agent_cfg, agent_key, service)
        ok_codes = frozenset({200, 301, 302, 401, 403})
        root_url = f"http://127.0.0.1:{port}/"
        candidates = _probe_urls_for_docker(root_url, container=container, internal_port=port)
        if not _probe_first(candidates, ok_codes=ok_codes):
            _ensure_hermes_dashboards()
            for _ in range(wait_sec):
                if _probe_first(candidates, ok_codes=ok_codes):
                    break
                time.sleep(1)
        if not _probe_first(candidates, ok_codes=ok_codes):
            print(f"[ERROR] Hermes dashboard 不可用: {url}", file=sys.stderr)
            return 1
        if not _running_in_mailbus_docker():
            _start_browser(url)
        print(f"Launched {agent_key} (browser) {url}")
        return 0

    if kind == "url_only":
        url = _subst(merged.get("url", "http://localhost:18789"), agent=agent_key)
        _start_browser(url)
        print(f"Launched {agent_key} (browser) {url}")
        return 0

    print(f"[ERROR] 未知 browser kind '{kind}' for agent {agent_key}", file=sys.stderr)
    return 1


def _python_exe() -> str:
    if sys.executable:
        return sys.executable
    from shutil import which

    return which("python3") or which("python") or "python"


def _resolve_interactive_cmd(agent_key: str, data_dir: str, merged: dict) -> str:
    resolver = os.path.join(ROOT, "tools", "resolve-agent-cli.py")
    r = run([_python_exe(), resolver, agent_key, "--mode", "interactive", "--data-dir", data_dir], timeout=30)
    cmd = (r.stdout or "").strip()
    if cmd:
        return cmd
    cmd = merged.get("command", "")
    session = str(merged.get("session", "main"))
    paths = mailbus_paths()
    hermes_home = str(merged.get("hermes_home", paths["hermes_data"]))
    profile_args = str(merged.get("profile_args", ""))
    return _subst(cmd, session=session, hermes_home=hermes_home, profile_args=profile_args, agent=agent_key)


def _launch_cli(agent_key: str, data_dir: str, merged: dict, agent_type: str) -> int:
    template = merged.get("_template", "")

    if agent_type == "claude_code" or template == "claude_host":
        launch_claude_cli(agent_key, data_dir)
        print(f"Launched {agent_key} (cli)")
        return 0

    cmd = _resolve_interactive_cmd(agent_key, data_dir, merged)
    if not cmd:
        print(f"[ERROR] agent {agent_key} 未配置 CLI", file=sys.stderr)
        return 1
    if not _start_wsl_interactive(cmd, agent_key):
        print(f"[ERROR] 无法启动 WSL 交互窗口", file=sys.stderr)
        return 1
    print(f"Launched {agent_key} (cli)")
    return 0


def launch_agent(agent_key: str, mode: str, data_dir: str) -> int:
    cfg = json_read(_config_path(data_dir), {})
    agents = cfg.get("agents") or {}
    if agent_key not in agents:
        print(f"[ERROR] agent '{agent_key}' not found", file=sys.stderr)
        return 1

    if mode == "desktop":
        if not agent_has_desktop(agents[agent_key], cfg.get("agent_types")):
            print(f"[ERROR] agent {agent_key} 未配置 launch.desktop", file=sys.stderr)
            return 1
        launch_desktop(agent_key, data_dir)
        print(f"Launched {agent_key} (desktop)")
        return 0

    merged = _merged_launch(cfg, agent_key, mode)
    if mode == "browser":
        return _launch_browser(agent_key, data_dir, merged, cfg)
    return _launch_cli(agent_key, data_dir, merged, agents[agent_key].get("type", ""))


def main(argv: list[str] | None = None) -> int:
    init_stdio()
    ap = argparse.ArgumentParser(description="Launch mailbus agent (browser/cli/desktop)")
    ap.add_argument("agent")
    ap.add_argument("mode", nargs="?", default="browser", choices=("browser", "cli", "desktop"))
    ap.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA") or os.path.join(ROOT, "store"))
    args = ap.parse_args(argv)
    load_mailbus_env()
    return launch_agent(args.agent, args.mode, args.data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
