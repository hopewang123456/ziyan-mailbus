#!/usr/bin/env python3
"""DeepSeek 平台浏览器启动：codex_docker/claude_host browser + 关闭 Desktop。"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "store", "config.json")

CODEX_BROWSER_DEFAULT = {
    "kind": "codex_docker",
    "url": "http://127.0.0.1:{port}/",
    "start_wait_seconds": 15,
}

CLAUDE_BROWSER_DEFAULT = {
    "kind": "claude_ttyd",
    "url": "http://127.0.0.1:{port}/",
    "start_wait_seconds": 15,
}

CODEX_AGENTS = {
    "lingxiao": {"web_port": "9240", "ttyd_url": "http://127.0.0.1:9250/"},
    "lingjian": {"web_port": "9241", "ttyd_url": "http://127.0.0.1:9251/"},
}

CLAUDE_AGENTS = {
    "lingyun": {"web_port": "9260"},
    "lingyan": {"web_port": "9261"},
}


def _merge_launch(agent: dict, *, template: str, browser: dict, desktop_enabled: bool = False) -> None:
    launch = dict(agent.get("launch") or {})
    launch["template"] = template
    launch["has_browser"] = True
    launch["launch_via_api"] = True
    merged_browser = dict(browser)
    merged_browser.update(launch.get("browser") or {})
    launch["browser"] = merged_browser
    desktop = dict(launch.get("desktop") or {})
    desktop["enabled"] = desktop_enabled
    if not desktop_enabled:
        desktop.pop("kind", None)
    launch["desktop"] = desktop
    agent["launch"] = launch


def main() -> None:
    with open(CONFIG, encoding="utf-8") as f:
        d = json.load(f)

    at = d.setdefault("agent_types", {})
    lt = at.setdefault("launch_templates", {})

    lt["codex_docker"] = {
        "cli": {"kind": "shell", "start_wait_seconds": 5},
        "browser": {
            **CODEX_BROWSER_DEFAULT,
            "web_port": "9240",
            "ttyd_url": "http://127.0.0.1:9250/",
        },
        "desktop": {"enabled": False, "kind": "codex_desktop"},
    }
    lt["claude_host"] = {
        "cli": {"kind": "shell", "start_wait_seconds": 0},
        "browser": {
            **CLAUDE_BROWSER_DEFAULT,
            "web_port": "9260",
        },
        "desktop": {"enabled": False, "kind": "claude_interactive"},
    }

    agents = d.setdefault("agents", {})
    for name, ports in CODEX_AGENTS.items():
        if name not in agents:
            continue
        browser = {**CODEX_BROWSER_DEFAULT, **ports}
        _merge_launch(agents[name], template="codex_docker", browser=browser, desktop_enabled=False)

    for name, ports in CLAUDE_AGENTS.items():
        if name not in agents:
            continue
        browser = {**CLAUDE_BROWSER_DEFAULT, **ports}
        _merge_launch(agents[name], template="claude_host", browser=browser, desktop_enabled=False)

    mc = d.setdefault("mailbus_claude", {"platform": "auto"})
    for plat in ("windows", "linux"):
        block = mc.setdefault(plat, {})
        block.setdefault("enabled", plat == "windows")
        block["browser_ports"] = {
            "lingyun": 9260,
            "lingyan": 9261,
        }
        block.setdefault("ttyd_bin", "ttyd")
        block.setdefault("ensure_on_launch", True)
        roots = dict(block.get("default_project_roots") or {})
        win_root = r"E:\ai_tools"
        lin_root = "/mnt/e/ai_tools"
        default = win_root if plat == "windows" else lin_root
        roots.setdefault("lingyun", default)
        roots.setdefault("lingyan", default)
        block["default_project_roots"] = roots

    mcx = d.setdefault("mailbus_codex", {"platform": "auto"})
    for plat in ("windows", "linux"):
        block = mcx.setdefault(plat, {})
        block.setdefault("sync_on_launch", True)
        block.setdefault("ensure_gateway_container", True)

    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    print("patched", CONFIG)


if __name__ == "__main__":
    main()
