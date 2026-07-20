#!/usr/bin/env python3
"""Audit agent launch ports — 解析端口 vs 默认表 vs HTTP 探针。"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from lib.env_bootstrap import load_mailbus_env, mailbus_paths  # noqa: E402
from lib.launch_ports import audit_agent_port, resolve_port  # noqa: E402
from lib.platform_runner import probe_http  # noqa: E402
from lib.utils import json_read  # noqa: E402


def _merged_browser(cfg: dict, agent_types: dict, agent_key: str) -> dict:
    agent = (cfg.get("agents") or {}).get(agent_key) or {}
    launch = agent.get("launch") or {}
    tmpl_name = launch.get("template", "")
    tmpl = (agent_types.get("launch_templates") or {}).get(tmpl_name, {})
    merged = dict(tmpl.get("browser") or {})
    merged.update(launch.get("browser") or {})
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit mailbus agent launch ports")
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", ""))
    ap.add_argument("--probe", action="store_true", help="HTTP probe resolved port")
    args = ap.parse_args()
    load_mailbus_env()
    paths = mailbus_paths()
    data_dir = args.data_dir or paths["data_dir"]
    cfg_path = os.path.join(data_dir, "config.json")
    cfg = json_read(cfg_path, {})
    agents = cfg.get("agents") or {}
    agent_types = cfg.get("agent_types") or {}

    fails = 0
    print(f"config={cfg_path}\n")
    for key in sorted(agents):
        agent_cfg = agents[key]
        launch = agent_cfg.get("launch") or {}
        if not launch.get("has_browser", True):
            continue
        browser = _merged_browser(cfg, agent_types, key)
        audit = audit_agent_port(key, agent_cfg, browser)
        port = audit["port"]
        launch_url = ""
        tmpl = launch.get("template", "")
        if port is not None:
            url_tpl = browser.get("url") or "http://127.0.0.1:{port}/"
            launch_url = url_tpl.replace("{port}", str(port)).replace("{agent}", key)
        probe_ok = None
        if args.probe and port is not None:
            probe_ok = probe_http(
                f"http://127.0.0.1:{port}/",
                ok_codes=frozenset({200, 301, 302, 401, 403, 404}),
            )
            if not probe_ok and tmpl == "hermes_dashboard":
                probe_ok = probe_http(
                    launch_url or f"http://127.0.0.1:{port}/chat",
                    ok_codes=frozenset({200, 301, 302, 401, 403, 404}),
                )
        mark = "OK"
        if port is None:
            mark = "WARN"
            fails += 1
        elif args.probe and probe_ok is False:
            mark = "DOWN"
            fails += 1
        probe_s = "" if probe_ok is None else (" up" if probe_ok else " down")
        print(
            f"{mark:4} {key:10} type={audit['type']:16} port={port!s:5} "
            f"src={audit['source']:22} group={audit['group']}{probe_s}"
        )
        if launch_url:
            print(f"      url={launch_url}")

    print(f"\nDone: {fails} issue(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
