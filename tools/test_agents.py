#!/usr/bin/env python3
"""
Agent 通用测试工具 — 从 store/config.json 读取全部 agent，逐项验证后输出报表。

覆盖项：
  1. 配置完整性（字段/模板匹配）
  2. 容器状态（docker ps）
  3. 浏览器 URL 可达性（HTTP probe）
  4. 身份文件（SOUL.md / IDENTITY.md）— 优先 API，回退本地文件
  5. AgentMemory 连通性

用法：
  python tools/test_agents.py              # 全部 agent
  python tools/test_agents.py agent-a     # 单个 agent
  python tools/test_agents.py --json       # JSON 输出（CI）
  python tools/test_agents.py --data-dir ./store
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ── 路径解析 ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = os.environ.get("MAILBUS_DATA") or os.environ.get("MAILBUS_DATA_DIR") or str(ROOT / "store")
LOCAL_HERMES = ROOT / ".local" / "hermes" / "profiles"

MAILBUS_API = os.environ.get("MAILBUS_API_URL") or (
    "http://mailbus:9814"
    if os.path.exists("/.dockerenv")
    else "http://127.0.0.1:9814"
)

AGENTMEMORY_URL = os.environ.get("AGENTMEMORY_URL") or (
    "http://iii-engine:3111"
    if os.path.exists("/.dockerenv")
    else "http://127.0.0.1:3111"
)


def _config_path(data_dir: str) -> str:
    return os.path.join(data_dir, "config.json")


def load_config(data_dir: str) -> dict:
    with open(_config_path(data_dir), encoding="utf-8") as f:
        return json.load(f)


# ── HTTP 探测 ─────────────────────────────────────────────────────────
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
                                     headers={"User-Agent": "mailbus-agent-test/1.0"})
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


# ── Mailbus API 调用 ──────────────────────────────────────────────────
def _api_get(path: str, timeout: float = 10.0) -> dict:
    try:
        url = f"{MAILBUS_API.rstrip('/')}{path}"
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "mailbus-agent-test/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return {}


def _api_available() -> bool:
    try:
        r = probe_http(f"{MAILBUS_API}/api/heartbeat", timeout=3.0)
        return r["ok"]
    except Exception:
        return False


# ── Docker 容器探测 ───────────────────────────────────────────────────
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


# ── 身份文件检查 ─────────────────────────────────────────────────────
def check_identity_via_api(agent: str) -> dict:
    """通过 Mailbus API 检查身份文件（绕过 host 文件系统权限问题）。"""
    profile = _api_get(f"/api/agent-profile/{agent}")
    if not profile or "error" in profile:
        return {"ok": False, "path": None, "size": 0, "error": "api_unavailable"}

    paths = profile.get("paths") or {}
    if paths.get("identity_ok") or paths.get("soul_ok"):
        ip = paths.get("identity") or paths.get("soul")
        return {"ok": True, "path": ip, "size": 0, "error": None}
    if paths.get("cards_ok"):
        return {"ok": True, "path": paths.get("cards_file"), "size": 0, "error": None}

    configured = paths.get("configured_identity")
    if configured:
        return {"ok": False, "path": configured, "size": 0, "error": "file_missing"}
    return {"ok": False, "path": None, "size": 0, "error": "not_configured"}


def check_identity_local(agent: str, atype: str) -> dict:
    """本地文件检查（回退，host 上 .local/ 可能有权限问题）。"""
    out = {"path": None, "ok": False, "error": None, "size": 0}

    if atype in ("hermes", "hermes_profile"):
        candidates = [
            str(LOCAL_HERMES / agent / "SOUL.md"),
            str(ROOT / "store" / "identities" / agent / "SOUL.md"),
        ]
    elif atype == "codex":
        candidates = [
            str(ROOT / "store" / "identities" / "codex" / agent / "IDENTITY.md"),
            str(ROOT / "access" / "codex" / agent / "IDENTITY.md"),
        ]
    elif atype == "claude_code":
        candidates = [
            str(ROOT / "store" / "identities" / "claude" / agent / "IDENTITY.md"),
        ]
    elif atype == "openclaw":
        candidates = [
            str(ROOT / "store" / "identities" / agent / "SOUL.md"),
            str(ROOT / "store" / "identities" / agent / "IDENTITY.md"),
        ]
    elif atype == "opencode":
        candidates = []
    else:
        candidates = []

    for p in candidates:
        if not p:
            continue
        try:
            if not os.path.isfile(p):
                continue
            size = os.path.getsize(p)
            with open(p, encoding="utf-8", errors="replace") as f:
                content = f.read(500)
            if len(content.strip()) > 20:
                out["path"] = p
                out["ok"] = True
                out["size"] = size
                return out
            out["path"] = p
            out["error"] = "too_short"
            out["size"] = size
            return out
        except (PermissionError, OSError):
            continue  # host .local/ 不可访问 → 跳过
        except Exception as exc:
            out["path"] = p
            out["error"] = str(exc)[:100]
            return out

    if candidates:
        out["error"] = "not_found"
    else:
        out["error"] = "not_applicable"
    return out


def check_identity(agent: str, atype: str, use_api: bool = True) -> dict:
    """优先 API，回退本地文件。"""
    if use_api:
        result = check_identity_via_api(agent)
        if result.get("ok") or result.get("error") == "api_unavailable":
            return result
    return check_identity_local(agent, atype)


# ── AgentMemory 检查 ─────────────────────────────────────────────────
def check_agentmemory() -> dict:
    for ep in ("/agentmemory/health", "/health", "/"):
        url = f"{AGENTMEMORY_URL.rstrip('/')}{ep}"
        r = probe_http(url, timeout=3.0)
        if r["ok"]:
            return {"url": url, "ok": True, "status": r["status"], "fix_hint": ""}
    return {
        "url": AGENTMEMORY_URL,
        "ok": False,
        "status": None,
        "error": "unreachable",
        "fix_hint": "AgentMemory 服务不可达。进入 docker-agents/ 目录执行 docker compose up -d iii-engine agentmemory 启动, 或用 docker compose restart iii-engine agentmemory 重启",
    }


# ── launch 配置 ──────────────────────────────────────────────────────
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
    """解析 agent 端口：优先 mailbus launch_ports 模块，回退 launch-ports.json。"""
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

    # 回退：launch-ports.json 直接读
    try:
        ports_path = ROOT / "config" / "mailbus" / "launch-ports.json"
        with open(ports_path) as f:
            ports = json.load(f)

        atype = agent_cfg.get("type", "")
        group_map = {
            "hermes": "hermes_dashboard",
            "hermes_profile": "hermes_dashboard",
            "codex": "codex_web",
            "openclaw": "openclaw_gateway",
            "claude_code": "claude_browser",
        }
        group = group_map.get(atype, "")
        if group and group in ports:
            return ports[group].get(agent) or ports[group].get("_fallback")
    except Exception:
        pass
    return None


def _browser_url(agent_cfg: dict, agent_types: dict) -> str:
    merged = _merged_browser(agent_cfg, agent_types)
    url = merged.get("url", "").strip()
    if not url:
        return ""

    agent = agent_cfg.get("_key", "")
    if not agent:
        return url

    port = _resolve_port(agent, agent_cfg, agent_types)
    if port is not None:
        url = url.replace("{port}", str(port))
    url = url.replace("{agent}", agent)
    return url


# ── 容器名解析 ───────────────────────────────────────────────────────
def _find_container(running: set[str], patterns: list[str]) -> str | None:
    """从运行中的容器列表里匹配容器名。
    匹配规则：pat 必须是容器名中的完整名称段（以 `-` 或边界分隔）。
    例如 'agent-d' 不会匹配 'docker-agents-codex-web-1'。
    """
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

    # 直接配置了容器名
    container = docker.get("container", "")
    if container and container in running:
        return container

    service = docker.get("service", "")

    # 按优先级匹配：agent 名 > service 名 > 类型名
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


# ── 单个 agent 测试 ──────────────────────────────────────────────────
def check_agent(name: str, cfg: dict, agent_types: dict,
               running: set[str], use_api: bool) -> dict:
    atype = cfg.get("type", "?")
    has_br = _has_browser(cfg, agent_types)
    result = {
        "agent": name,
        "display": cfg.get("name", name),
        "type": atype,
        "checks": {},
    }

    # 1) 配置完整性
    tmpl_name = (cfg.get("launch") or {}).get("template", "")
    launch_templates = agent_types.get("launch_templates") or {}
    tmpl_exists = bool(tmpl_name and launch_templates.get(tmpl_name))
    role_ok = bool(cfg.get("role") or cfg.get("archetype"))
    config_detail = f"template={tmpl_name or '?'}, role={'yes' if role_ok else 'no'}"
    if not tmpl_exists:
        if not tmpl_name:
            config_fix = "缺少 launch.template，请在 agent 配置中添加对应的启动模板名称"
        else:
            config_fix = f"launch template '{tmpl_name}' 未在 agent_types.launch_templates 中定义，检查 store/config.json"
    elif not role_ok:
        config_fix = "缺少 role/archetype 字段，在配置中为该 agent 补充角色信息"
    else:
        config_fix = ""
    result["checks"]["config"] = {
        "ok": bool(tmpl_exists),
        "detail": config_detail,
        "fix_hint": config_fix,
    }

    # 2) 容器状态
    service = (cfg.get("docker") or {}).get("service", "")
    if atype in ("hermes", "hermes_profile", "codex", "openclaw", "opencode"):
        container = _resolve_container(cfg, running)
        if container:
            result["checks"]["container"] = {
                "ok": True,
                "detail": f"{container} running",
                "fix_hint": "",
            }
        else:
            svc = service or {"hermes": "hermes", "hermes_profile": "hermes",
                              "codex": "codex-agent", "openclaw": "openclaw",
                              "opencode": "opencode"}.get(atype, atype)
            result["checks"]["container"] = {
                "ok": False,
                "detail": f"container not found (type={atype})",
                "fix_hint": f"Docker 容器未运行。执行 docker compose up -d {svc} 启动，或检查 docker compose 配置",
            }
    elif atype == "claude_code":
        result["checks"]["container"] = {"ok": True, "detail": "host", "fix_hint": ""}
    else:
        result["checks"]["container"] = {"ok": True, "detail": "n/a", "fix_hint": ""}

    # 3) 浏览器 URL
    if has_br:
        url = _browser_url(cfg, agent_types)
        if url and "{" in url:
            result["checks"]["browser"] = {
                "ok": False,
                "detail": f"unresolved placeholder: {url}",
                "fix_hint": "端口占位符未替换。在 config/mailbus/launch-ports.json 中为该 agent 设置端口，或检查 agent_types 中的 browser.url 模板",
            }
        elif url:
            probe = probe_http(url)
            status_code = probe.get("status")
            if probe["ok"]:
                fix = ""
            elif status_code and 400 <= status_code < 500:
                fix = f"浏览器返回 HTTP {status_code}。可能是鉴权问题：检查 docker-compose.yml 中的 HERMES_DASHBOARD_BASIC_AUTH 环境变量是否已移除，或检查 agent 的 API key 配置"
            elif status_code and status_code >= 500:
                fix = "浏览器端口可达但服务内部错误 (5xx)。检查容器日志：docker logs <container>"
            else:
                fix = "浏览器端口不可达。确认容器已启动且端口映射正确（docker-compose.yml ports 段），或等待容器 health check 通过后重试"
            result["checks"]["browser"] = {
                "ok": probe["ok"],
                "detail": f"{url} -> HTTP {status_code or probe.get('error')}",
                "fix_hint": fix,
            }
        else:
            result["checks"]["browser"] = {
                "ok": False,
                "detail": "url resolve failed",
                "fix_hint": "浏览器 URL 无法解析。在 agent_types.launch_templates 中检查该类型 browser.url 是否配置，或在 agent 自身 launch.browser 中补充 url",
            }
    else:
        result["checks"]["browser"] = {"ok": True, "detail": "no browser", "fix_hint": ""}

    # 4) 身份文件
    identity = check_identity(name, atype, use_api=use_api)
    if identity["ok"] and identity["path"]:
        detail = f"{identity['path']} ({identity.get('size', 0)}B)"
        fix = ""
    elif identity["ok"]:
        detail = "via Mailbus API"
        fix = ""
    else:
        err_type = identity.get("error", "not found")
        detail = err_type
        if err_type == "api_unavailable":
            fix = "Mailbus API 不可用，无法通过 API 检测身份文件。重启 mailbus 服务后重试"
        elif err_type == "file_missing":
            fix = f"身份文件路径已配置但文件不存在。运行 mailbus init-store 或从 Obsidian Vault 同步对应 agent 的 _card.md/IDENTITY.md 到 store/identities/"
        elif err_type == "not_configured":
            fix = "该 agent 未配置身份文件。在 Obsidian Vault Agent 目录下为该 agent 创建 _card.md，然后用 mailbus init-store 同步"
        elif err_type == "too_short":
            fix = f"身份文件存在但内容过短 ({identity.get('size', 0)}B)。请检查 Obsidian Vault 中的 _card.md 是否有完整内容"
        else:
            fix = "身份文件缺失。检查 Obsidian Vault 中的 agent 卡片是否已创建并同步到 store/identities/"
    result["checks"]["identity"] = {
        "ok": identity["ok"],
        "detail": detail,
        "fix_hint": fix,
    }

    # 5) 汇总
    result["pass"] = all(v["ok"] for v in result["checks"].values())
    return result


# ── 输出 ──────────────────────────────────────────────────────────────
STATUS_OK = {True: "PASS", False: "FAIL"}


def print_report(results: list[dict], am_check: dict):
    print()
    print("=" * 72)
    print("  Mailbus Agent 通用测试报告")
    print("=" * 72)

    am_ok = am_check["ok"]
    am_icon = "PASS" if am_ok else "FAIL"
    print(f"\n  AgentMemory: {am_icon}  {am_check.get('url', '?')}"
          f"  (HTTP {am_check.get('status') or am_check.get('error')})")

    hdr = (f"\n  {'Agent':<12} {'类型':<16} {'容器':<10} {'浏览器':<10}"
           f" {'身份':<10} {'配置':<10}")
    print(hdr)
    print("  " + "-" * 66)

    for r in results:
        c = r["checks"]
        line = (
            f"  {r['display']:<12} {r['type']:<16} "
            f"{STATUS_OK[c['container']['ok']]:<10} "
            f"{STATUS_OK[c['browser']['ok']]:<10} "
            f"{STATUS_OK[c['identity']['ok']]:<10} "
            f"{STATUS_OK[c['config']['ok']]:<10}"
        )
        print(line)

    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    print(f"\n  Result: {passed}/{total} passed")
    if passed < total:
        print("\n  Details of failures:")
        for r in results:
            if not r["pass"]:
                print(f"\n  [{r['display']}]")
                for check_name, check in r["checks"].items():
                    if not check["ok"]:
                        print(f"    {check_name}: {check['detail']}")
    print()


def print_json_report(results: list[dict], am_check: dict):
    print(json.dumps({
        "agentmemory": am_check,
        "agents": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r["pass"]),
        },
    }, ensure_ascii=False, indent=2))


# ── CLI ───────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Agent test tool")
    ap.add_argument("agent", nargs="?", default="", help="test specific agent")
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                    help=f"data directory (default: {DEFAULT_DATA_DIR})")
    ap.add_argument("--json", action="store_true", help="JSON output for CI")
    ap.add_argument("--no-api", action="store_true",
                    help="skip Mailbus API for identity check (use local files only)")
    args = ap.parse_args(argv)

    if not os.path.isfile(_config_path(args.data_dir)):
        print(f"[ERROR] config not found: {_config_path(args.data_dir)}", file=sys.stderr)
        return 1

    cfg = load_config(args.data_dir)
    agents = cfg.get("agents") or {}
    agent_types = cfg.get("agent_types") or {}

    if not agents:
        print("[ERROR] no agents in config", file=sys.stderr)
        return 1

    for k, v in agents.items():
        v["_key"] = k

    if args.agent:
        if args.agent not in agents:
            print(f"[ERROR] agent '{args.agent}' not found", file=sys.stderr)
            print(f"  available: {', '.join(sorted(agents.keys()))}")
            return 1
        target = {args.agent: agents[args.agent]}
    else:
        target = agents

    running = _running_containers()
    use_api = not args.no_api and _api_available()
    am_check = check_agentmemory()

    results = []
    for name in sorted(target.keys()):
        try:
            results.append(check_agent(name, target[name], agent_types, running, use_api))
        except Exception as exc:
            results.append({
                "agent": name, "display": name, "type": "?",
                "checks": {"error": {"ok": False, "detail": str(exc)[:200]}},
                "pass": False,
            })

    if args.json:
        print_json_report(results, am_check)
    else:
        print_report(results, am_check)

    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
