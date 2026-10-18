#!/usr/bin/env python3
"""mailbus 全景体检 — 一屏汇总每个 agent 的浏览器/CLI/容器/身份可达性 + 第三方组件健康。

输出统一 JSON（--json）或人类可读表。

用法：
  python tools/health-overview.py              # 全部 agent + 服务，人类可读表
  python tools/health-overview.py --json       # JSON 输出（诊所前端用）
  python tools/health-overview.py --data-dir ./store
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

DEFAULT_DATA_DIR = os.environ.get("MAILBUS_DATA") or os.environ.get("MAILBUS_DATA_DIR") or str(ROOT / "shared" / "store")


def _config_path(data_dir: str) -> str:
    return os.path.join(data_dir, "config.json")


def load_config(data_dir: str) -> dict:
    with open(_config_path(data_dir), encoding="utf-8") as f:
        return json.load(f)


def probe_http(url: str, timeout: float = 5.0, ok_codes: frozenset | None = None) -> dict:
    if ok_codes is None:
        ok_codes = frozenset(range(200, 500))
    out = {"url": url, "ok": False, "status": None, "error": None}
    if not url:
        out["error"] = "empty_url"
        return out
    probed = url
    try:
        from lib.infra.runtime_net import resolve_loopback

        probed = resolve_loopback(url)
    except Exception:
        pass
    try:
        req = urllib.request.Request(probed, method="GET",
                                     headers={"User-Agent": "mailbus-health-overview/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out["status"] = resp.getcode()
            out["ok"] = resp.getcode() in ok_codes
            return out
    except urllib.error.HTTPError as exc:
        out["status"] = exc.code
        out["ok"] = exc.code in ok_codes
        out["error"] = f"HTTP {exc.code}"
        return out
    except Exception as exc:
        out["error"] = str(exc)[:200]
        return out


def _running_containers() -> set[str]:
    """运行中容器名集合：本机 docker 优先，Windows 无 docker CLI 时经 wsl -e docker 双探。"""
    try:
        from lib.adapters.ops.doctor_checks import docker_status
        from lib.adapters.plane.platform_runner import docker_argv, run, wsl_exe

        dstat = docker_status()
        if not dstat.get("ready"):
            return set()
        if dstat.get("source") == "wsl":
            wsl = wsl_exe()
            if not wsl:
                return set()
            r = run(
                [wsl, "-d", "Ubuntu", "-e", "bash", "-lc",
                 "docker ps --format '{{.Names}}'"],
                timeout=10,
            )
        else:
            r = run(docker_argv("ps", "--format", "{{.Names}}"), timeout=10)
        if r.returncode == 0:
            return set(r.stdout.strip().splitlines())
    except Exception:
        pass
    return set()


def _find_container(running: set[str], patterns: list[str]) -> str | None:
    for pat in patterns:
        for c in sorted(running):
            segments = c.replace("-", " ").split()
            if pat in segments:
                return c
    return None


def _resolve_container(agent_cfg: dict, running: set[str]) -> str | None:
    atype = agent_cfg.get("type", "")
    agent_name = agent_cfg.get("_key", "")
    docker = agent_cfg.get("docker") or {}
    container = docker.get("container", "")
    if container and container in running:
        return container
    service = docker.get("service", "")
    if agent_name:
        c = _find_container(running, [agent_name])
        if c:
            return c
    if atype in ("hermes", "hermes_profile"):
        return _find_container(running, ["hermes"])
    if atype == "codex":
        return _find_container(running, ["codex"])
    if atype == "openclaw":
        return _find_container(running, ["openclaw"])
    if atype == "opencode":
        return _find_container(running, ["opencode"])
    if service:
        return _find_container(running, [service])
    return None


def _merged_browser(agent_cfg: dict, agent_types: dict) -> dict:
    launch = agent_cfg.get("launch") or {}
    tmpl_name = launch.get("template", "")
    tmpl = (agent_types.get("launch_templates") or {}).get(tmpl_name, {}) or {}
    merged = dict(tmpl.get("browser") or {})
    merged.update(launch.get("browser") or {})
    return merged


def _has_browser(agent_cfg: dict, agent_types: dict) -> bool:
    launch = agent_cfg.get("launch") or {}
    if "has_browser" in launch:
        return bool(launch["has_browser"])
    merged = _merged_browser(agent_cfg, agent_types)
    kind = (merged.get("kind") or "").strip()
    return bool(kind) and kind != "none"


def _resolve_port(agent: str, agent_cfg: dict, agent_types: dict) -> int | None:
    try:
        from lib.adapters.config.launch_ports import resolve_port

        launch = agent_cfg.get("launch") or {}
        tmpl_name = launch.get("template", "")
        tmpl = (agent_types.get("launch_templates") or {}).get(tmpl_name, {}) or {}
        browser_cfg = dict(tmpl.get("browser") or {})
        browser_cfg.update(launch.get("browser") or {})
        return resolve_port(agent, agent_cfg, browser_cfg)
    except Exception:
        pass
    return None


def _browser_url(agent: str, agent_cfg: dict, agent_types: dict) -> str:
    merged = _merged_browser(agent_cfg, agent_types)
    url = (merged.get("url") or "").strip()
    if not url:
        return ""
    port = _resolve_port(agent, agent_cfg, agent_types)
    if port is not None:
        url = url.replace("{port}", str(port))
    url = url.replace("{agent}", agent)
    # OpenClaw gateway 自动带 token 免密（与 handlers_system._get_launch_url 一致）
    atype = agent_cfg.get("type", "")
    if atype == "openclaw" or (agent_cfg.get("launch") or {}).get("template") == "openclaw_gateway":
        url = _with_gateway_token(url)
    return url


def _with_gateway_token(url: str) -> str:
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if not token or not url:
        return url
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["token"] = [token]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def check_identity_local(agent: str, atype: str) -> dict:
    out = {"path": None, "ok": False, "error": None}
    local_hermes = ROOT / ".local" / "hermes" / "profiles"
    if atype in ("hermes", "hermes_profile"):
        candidates = [str(local_hermes / agent / "SOUL.md"),
                      str(ROOT / "shared" / "store" / "identities" / agent / "SOUL.md"),
                      str(ROOT / "shared" / "store" / "identities" / "hermes" / agent / "SOUL.md"),
                      str(ROOT / "shared" / "store" / "identities" / "hermes" / agent / "IDENTITY.md")]
    elif atype == "codex":
        candidates = [str(ROOT / "shared" / "store" / "identities" / "codex" / agent / "IDENTITY.md")]
    elif atype == "claude_code":
        candidates = [str(ROOT / "shared" / "store" / "identities" / "claude" / agent / "IDENTITY.md")]
    elif atype == "openclaw":
        candidates = [
            str(ROOT / "shared" / "store" / "identities" / "openclaw" / agent / "IDENTITY.md"),
            str(ROOT / "shared" / "store" / "identities" / "openclaw" / agent / "SOUL.md"),
            str(ROOT / "shared" / "store" / "identities" / agent / "SOUL.md"),
            str(ROOT / "shared" / "store" / "identities" / agent / "IDENTITY.md"),
        ]
    elif atype == "opencode":
        candidates = [
            str(ROOT / "shared" / "store" / "identities" / "opencode" / agent / "IDENTITY.md"),
            str(ROOT / "shared" / "store" / "identities" / "opencode" / agent / "SOUL.md"),
            str(ROOT / "shared" / "store" / "identities" / agent / "IDENTITY.md"),
        ]
    elif atype == "cursor":
        candidates = [
            str(ROOT / "shared" / "store" / "identities" / "cursor" / agent / "IDENTITY.md"),
            str(ROOT / "shared" / "store" / "identities" / agent / "IDENTITY.md"),
        ]
    else:
        candidates = []
    for p in candidates:
        if not p:
            continue
        try:
            if not os.path.isfile(p):
                continue
            with open(p, encoding="utf-8", errors="replace") as f:
                content = f.read(500)
            if len(content.strip()) > 20:
                out["path"] = p
                out["ok"] = True
                return out
            out["path"] = p
            out["error"] = "too_short"
            return out
        except (PermissionError, OSError):
            continue
        except Exception as exc:
            out["path"] = p
            out["error"] = str(exc)[:100]
            return out
    out["error"] = "not_found" if candidates else "not_applicable"
    return out


def check_agent(name: str, cfg: dict, agent_types: dict, running: set[str]) -> dict:
    atype = cfg.get("type", "?")
    checks: dict[str, dict] = {}

    # 1) 浏览器可达
    if _has_browser(cfg, agent_types):
        url = _browser_url(name, cfg, agent_types)
        if url and "{" in url:
            checks["browser"] = {"ok": False, "detail": f"unresolved placeholder: {url}"}
        elif url:
            probe = probe_http(url)
            checks["browser"] = {"ok": probe["ok"],
                                 "detail": f"{url} -> HTTP {probe.get('status') or probe.get('error')}"}
        else:
            checks["browser"] = {"ok": False, "detail": "url resolve failed"}
    else:
        checks["browser"] = {"ok": True, "detail": "no browser"}

    # 2) CLI 可达（命令可解析 + 容器运行）
    try:
        from lib.adapters.frameworks import resolve_push_cli

        cli = resolve_push_cli(name, cfg, agent_types)
        checks["cli"] = {"ok": bool(cli), "detail": cli[:120] if cli else "empty push cli"}
    except Exception as exc:
        err = str(exc)[:120]
        # mailbus 常跑在 Docker 内：无 /mnt/c PowerShell，但宿主机 ttyd/浏览器仍可用
        if atype == "claude_code" and "PowerShell" in err and checks.get("browser", {}).get("ok"):
            checks["cli"] = {
                "ok": True,
                "detail": f"host-bridge soft-ok (browser up; {err[:60]})",
            }
        else:
            checks["cli"] = {"ok": False, "detail": f"resolve error: {err[:80]}"}

    # cursor：无 cursor-agent 时走 file_bus，不算挂载失败
    if atype == "cursor" and not checks.get("cli", {}).get("ok"):
        checks["cli"] = {"ok": True, "detail": "file_bus (no cursor-agent binary)"}

    # 3) 容器状态
    if atype in ("hermes", "hermes_profile", "codex", "openclaw", "opencode"):
        container = _resolve_container({**cfg, "_key": name}, running)
        checks["container"] = {"ok": bool(container),
                               "detail": f"{container} running" if container else "container not found"}
    elif atype == "claude_code":
        checks["container"] = {"ok": True, "detail": "host"}
    else:
        checks["container"] = {"ok": True, "detail": "n/a"}

    # 4) 身份文件
    identity = check_identity_local(name, atype)
    if identity["ok"]:
        checks["identity"] = {"ok": True, "detail": identity["path"]}
    elif identity.get("error") == "not_applicable":
        checks["identity"] = {"ok": True, "detail": "n/a"}
    elif identity.get("error") == "not_found" and atype == "cursor":
        checks["identity"] = {"ok": True, "detail": "optional (cursor)"}
    else:
        checks["identity"] = {
            "ok": False,
            "detail": identity.get("error") or "not_found",
        }

    return {
        "agent": name,
        "display": cfg.get("name", name),
        "type": atype,
        "checks": checks,
        "pass": all(v["ok"] for v in checks.values()),
    }


def check_services(data_dir: str) -> dict[str, dict]:
    services: dict[str, dict] = {}

    # ollama / agentmemory 走 service_registry
    for name in ("ollama", "agentmemory"):
        try:
            from lib.adapters.ops.service_registry import probe_service

            services[name] = probe_service(name, data_dir=data_dir, timeout=5)
        except Exception as exc:
            services[name] = {"ok": False, "id": name, "error": str(exc)[:80]}

    # n8n
    n8n_url = os.environ.get("N8N_BASE_URL", "").strip()
    if n8n_url:
        p = probe_http(n8n_url, timeout=4.0, ok_codes=frozenset(range(200, 500)))
        services["n8n"] = {"ok": p["ok"], "base_url": n8n_url, "detail": f"HTTP {p.get('status') or p.get('error')}"}
    else:
        services["n8n"] = {"ok": True, "detail": "skipped (not_configured)", "skipped": True}

    # comfyui
    comfy_url = os.environ.get("COMFYUI_BASE_URL", "").strip()
    if comfy_url:
        p = probe_http(comfy_url, timeout=4.0, ok_codes=frozenset(range(200, 500)))
        if p["ok"]:
            services["comfyui"] = {
                "ok": True,
                "base_url": comfy_url,
                "detail": f"HTTP {p.get('status') or p.get('error')}",
            }
        else:
            # 可选集成：配了 URL 但未启动时不拖垮全景 ok
            services["comfyui"] = {
                "ok": True,
                "base_url": comfy_url,
                "detail": f"unreachable (optional): {p.get('status') or p.get('error')}",
                "skipped": True,
            }
    else:
        services["comfyui"] = {"ok": True, "detail": "skipped (not_configured)", "skipped": True}

    # external-tools（registry 中逐 provider 标配置状态）
    try:
        from lib.adapters.integrations.external_tools import load_registry

        reg = load_registry(data_dir)
        providers = (reg.get("providers") or {}) if isinstance(reg, dict) else {}
        if providers:
            for pname, pcfg in providers.items():
                base_env = (pcfg or {}).get("base_url_env", "")
                base = os.environ.get(base_env, "") if base_env else ""
                if base:
                    p = probe_http(base, timeout=4.0, ok_codes=frozenset(range(200, 500)))
                    if p["ok"]:
                        services[f"ext:{pname}"] = {
                            "ok": True,
                            "base_url": base,
                            "detail": f"HTTP {p.get('status') or p.get('error')}",
                        }
                    else:
                        services[f"ext:{pname}"] = {
                            "ok": True,
                            "base_url": base,
                            "detail": f"unreachable (optional): {p.get('status') or p.get('error')}",
                            "skipped": True,
                        }
                else:
                    services[f"ext:{pname}"] = {
                        "ok": True,
                        "detail": "skipped (not_configured)",
                        "skipped": True,
                    }
        else:
            services["external-tools"] = {"ok": True, "detail": "skipped (no providers)", "skipped": True}
    except Exception as exc:
        services["external-tools"] = {"ok": False, "detail": f"load error: {str(exc)[:80]}"}

    return services


def print_report(results: list[dict], services: dict[str, dict]):
    def ok_icon(ok: bool) -> str:
        return "OK " if ok else "FAIL"

    print()
    print("=" * 76)
    print("  Mailbus 全景体检")
    print("=" * 76)

    print("\n  ── Agents ──")
    print(f"  {'Agent':<12} {'类型':<16} {'浏览器':<8} {'CLI':<8} {'容器':<8} {'身份':<8}")
    print("  " + "-" * 70)
    for r in results:
        c = r["checks"]
        print(f"  {r['display']:<12} {r['type']:<16} {ok_icon(c['browser']['ok']):<8} "
              f"{ok_icon(c['cli']['ok']):<8} {ok_icon(c['container']['ok']):<8} "
              f"{ok_icon(c['identity']['ok']):<8}")
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    print(f"\n  Agents: {passed}/{total} 通过")

    print("\n  ── 第三方组件 ──")
    for name, s in sorted(services.items()):
        ok = bool(s.get("ok"))
        detail = s.get("detail") or s.get("base_url") or s.get("error") or ""
        print(f"  {ok_icon(ok)} {name:<16} {detail}")

    print()


def print_json(results: list[dict], services: dict[str, dict]):
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    required = {k: v for k, v in services.items() if not v.get("skipped")}
    svc_ok = sum(1 for s in required.values() if s.get("ok"))
    print(json.dumps({
        "agents": results,
        "services": services,
        "summary": {
            "agents_total": total,
            "agents_passed": passed,
            "services_total": len(required),
            "services_ok": svc_ok,
            "services_skipped": sum(1 for s in services.values() if s.get("skipped")),
            "ok": passed == total and svc_ok == len(required),
        },
    }, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="mailbus health overview")
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                    help=f"data directory (default: {DEFAULT_DATA_DIR})")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args(argv)

    if not os.path.isfile(_config_path(args.data_dir)):
        print(f"[ERROR] config not found: {_config_path(args.data_dir)}", file=sys.stderr)
        return 1

    cfg = load_config(args.data_dir)
    agents = cfg.get("agents") or {}
    agent_types = cfg.get("agent_types") or {}
    for k, v in agents.items():
        v["_key"] = k

    running = _running_containers()

    results = []
    for name in sorted(agents.keys()):
        try:
            results.append(check_agent(name, agents[name], agent_types, running))
        except Exception as exc:
            results.append({
                "agent": name, "display": name, "type": "?",
                "checks": {"error": {"ok": False, "detail": str(exc)[:200]}},
                "pass": False,
            })

    services = check_services(args.data_dir)

    if args.json:
        print_json(results, services)
        # JSON 模式恒返回 0：健康状态由 summary.ok 自描述，避免诊所 run 判定为执行失败
        return 0

    all_ok = all(r["pass"] for r in results) and all(s.get("ok") for s in services.values())
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
