"""
ziyan-mailbus HTTP API — 系统相关路由处理器

处理: /api/status, /api/agents, /api/heartbeat, /api/alerts,
      /api/config, /api/reports, /api/search, /api/templates,
      /api/agent-profile/, /api/ping/, /api/launch,
      /api/clinic/tools, /api/clinic/run
"""

import os
import json
import sys
import time
import shutil
import subprocess
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from lib.infra.constants import MAILBUS_ROOT
from lib.domain.models import Inbox
from lib.infra.utils import json_read, json_write, resolve_paths, resolve_mailbus_path, identity_candidates, to_wsl_path, _now_iso
from lib.adapters.ops.heartbeat import load_status as load_heartbeat
from lib.adapters.ops.alerter import get_recent_alerts
from lib.adapters.ops.scheduler import get_scheduler_status
from lib.infra.clock import now_dt, now_iso, now_ts, now_utc_dt


def _reload_store_config(handler) -> tuple[dict, dict]:
    """每次 API 请求从 config.json 重读 agents（避免 serve 进程缓存旧配置）。"""
    config_path = os.path.join(handler.data_dir, "config.json")
    cfg = json_read(config_path, {})
    agents = cfg.get("agents") or handler.agents or {}
    agent_types = cfg.get("agent_types") or handler.agent_types or {}
    handler.agents = agents
    handler.agent_types = agent_types
    return agents, agent_types


def _launch_script_timeout(mode: str) -> int:
    """Codex Web UI 冷启动可达 30s+，browser 超时须留余量。"""
    if mode == "desktop":
        return 90
    if mode == "browser":
        return 120
    return 30


def _running_in_mailbus_container() -> bool:
    from lib.adapters.plane.platform_runner import running_in_mailbus_docker

    return running_in_mailbus_docker()


def _resolve_launch_script_path() -> str:
    """定位 tools/ops/launch-agent.sh（容器 /mailbus 或源码树）。"""
    lib_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    for cand in (
        os.path.join(str(MAILBUS_ROOT), "tools", "ops", "launch-agent.sh"),
        os.path.join(lib_root, "tools", "ops", "launch-agent.sh"),
        "/mailbus/tools/ops/launch-agent.sh",
    ):
        if os.path.isfile(cand):
            return cand
    return ""


def _run_launch_script(script_path: str, agent: str, mode: str) -> subprocess.CompletedProcess:
    """在 WSL/bash 中执行 launch-agent.sh（Windows 原生 serve 走 wsl）。"""
    timeout = _launch_script_timeout(mode)
    run_kw: dict = {"capture_output": True, "timeout": timeout}
    if sys.platform == "win32":
        run_kw["encoding"] = "utf-8"
        run_kw["errors"] = "replace"
    else:
        run_kw["text"] = True
    if sys.platform == "win32":
        wsl = shutil.which("wsl.exe") or shutil.which("wsl")
        if wsl:
            wsl_script = to_wsl_path(script_path)
            return subprocess.run(
                [wsl, "-e", "bash", wsl_script, agent, mode],
                **run_kw,
            )
    bash = shutil.which("bash") or "bash"
    return subprocess.run(
        [bash, script_path, agent, mode],
        **run_kw,
    )


def handle_status(handler):
    """GET /api/status — 总线概要状态"""
    total = 0
    unread = 0
    agent_statuses = {}
    paths = resolve_paths(handler.data_dir)
    for name in handler.agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        data = json_read(inbox_file, [])
        if isinstance(data, list):
            count = len(data)
            has_unread = False
        else:
            count = len(data.get("messages", [])) if data else 0
            has_unread = data.get("has_unread", False) if data else False
        total += count
        if isinstance(data, dict) and "agent" in data:
            try:
                inbox = Inbox.from_dict(data)
                terminal_states = {"done", "closed", "rejected", "failed", "archived", "sent"}
                unread += sum(1 for m in inbox.messages
                              if (inbox.msg_field(m, "state") or inbox.msg_field(m, "status", ""))
                              not in terminal_states)
            except (KeyError, TypeError):
                pass
        agent_statuses[name] = {
            "active_messages": count,
            "has_unread": has_unread if isinstance(data, list) else (data.get("has_unread", False) if data else False),
            "type": handler.agents[name].get("type", "?"),
        }
    handler._send_json({
        "status": "ok",
        "version": "v2.0.0",
        "project": "ziyan-mailbus",
        "agents": len(handler.agents),
        "total_messages": total,
        "unread_messages": unread,
        "agent_statuses": agent_statuses,
        "scheduler": get_scheduler_status(),
        "round1_gate": json_read(
            os.path.join(handler.data_dir, "iterations", "round-1-gate.json"), {}
        ),
    })


def _parse_launch_stdout_url(stdout: str) -> str:
    """从 launch-agent.sh  stdout 末行提取 URL（Launched agent codex-ui http://...）。"""
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("Launched "):
            continue
        for token in line.split():
            if token.startswith("http://") or token.startswith("https://"):
                return token.rstrip(")")
    return ""


def _resolve_agent_browser_url(handler, agent_name: str) -> str:
    """解析 agent 浏览器 URL（Codex/Claude 含 per-agent 端口）。"""
    cfg = handler.agents.get(agent_name, {})
    atype = cfg.get("type", "")
    if atype == "claude_code":
        try:
            from lib.adapters.frameworks.claude_browser_launch import resolve_browser_url

            return resolve_browser_url(agent_name, handler.data_dir)
        except Exception:
            pass
    return _get_launch_url(handler, agent_name)


def _agent_launch_meta(handler, name: str, cfg: dict) -> dict:
    from lib.adapters.frameworks.desktop_launch import agent_has_desktop

    launch = cfg.get("launch") or {}
    atype = cfg.get("type", "?")
    launch_via_api = atype in ("codex", "claude_code") or bool(launch.get("launch_via_api"))
    has_desktop = agent_has_desktop(cfg, handler.agent_types)
    if atype in ("codex", "claude_code"):
        has_desktop = False

    # 无 browser kind / 显式关闭 → 不算有浏览器（避免 dali 等假 has_browser）
    has_browser = launch.get("has_browser")
    if has_browser is None:
        tmpl_name = launch.get("template", "")
        tmpl = (handler.agent_types.get("launch_templates") or {}).get(tmpl_name, {}) or {}
        kind = ((launch.get("browser") or {}).get("kind")
                or ((tmpl.get("browser") or {}).get("kind") or "")).strip()
        has_browser = bool(kind) and kind != "none"
    else:
        has_browser = bool(has_browser)

    launch_modes = ["cli"]
    if has_browser:
        launch_modes.insert(0, "browser")
    if has_desktop:
        launch_modes.append("desktop")
    return {
        "launch_modes": launch_modes,
        "has_browser": has_browser,
        "has_desktop": has_desktop,
        "launch_via_api": launch_via_api,
        "launch_url": _resolve_agent_browser_url(handler, name) if has_browser else "",
    }


def handle_agents(handler):
    """GET /api/agents — 获取 agent 列表和配置（含 access/agent.json registry）。"""
    from lib.adapters.config.agent_registry import get_agent, mailbus_root

    agents, _ = _reload_store_config(handler)
    canonical = str(mailbus_root()).replace("\\", "/")
    result = {}
    for name, cfg in agents.items():
        meta = _agent_launch_meta(handler, name, cfg)
        reg = get_agent(name) or {}
        entry = {
            "name": cfg.get("name", name),
            "role": cfg.get("role", ""),
            "type": cfg.get("type", "?"),
            "models": cfg.get("models", []),
            "webhook_url": cfg.get("webhook_url", ""),
            "archetype": reg.get("archetype") or cfg.get("archetype", ""),
            "framework": reg.get("framework") or cfg.get("type", ""),
            "canonical_root": canonical,
            "agent_json": reg.get("_rel_path", ""),
            **meta,
        }
        result[name] = entry
    handler._send_json({"agents": result, "canonical_root": canonical})


def handle_frameworks(handler):
    """GET /api/frameworks — framework discovery 状态（Dashboard 配置中心）。"""
    from ..framework_discovery import framework_status, scan_framework_agents

    out: dict = {}
    for fw, st in framework_status().items():
        entry = dict(st)
        entry["agents"] = scan_framework_agents(fw)
        out[fw] = entry
    handler._send_json({"frameworks": out})


def handle_workload(handler):
    """GET /api/workload — Agent 负载摘要（P2）。"""
    from lib.application.orchestration.tracker import TaskTracker

    paths = resolve_paths(handler.data_dir)
    tracker = TaskTracker(handler.data_dir)
    tasks = tracker.list_all()
    active_by_agent: dict = {}
    queued_by_agent: dict = {}
    for t in tasks:
        if t.get("status") not in ("running", "pending"):
            continue
        assignee = t.get("assignee") or ""
        if assignee:
            active_by_agent[assignee] = active_by_agent.get(assignee, 0) + 1
        for s in t.get("chain") or []:
            if not isinstance(s, dict):
                continue
            if s.get("fsm_state") in ("queued", "awaiting_result") or s.get("status") == "running":
                ag = s.get("to_agent") or s.get("to_person") or ""
                if ag:
                    queued_by_agent[ag] = queued_by_agent.get(ag, 0) + 1

    agents_out = {}
    for name in handler.agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        data = json_read(inbox_file, {})
        inbox_count = len(data.get("messages", [])) if isinstance(data, dict) else len(data or [])
        agents_out[name] = {
            "name": handler.agents[name].get("name", name),
            "role": handler.agents[name].get("role", ""),
            "active_tasks": active_by_agent.get(name, 0),
            "queued_steps": queued_by_agent.get(name, 0),
            "inbox_pending": inbox_count,
        }
    handler._send_json({"agents": agents_out, "generated_at": _now_iso()})


def handle_heartbeat(handler):
    """GET /api/heartbeat — 心跳状态"""
    hb_data = load_heartbeat(handler.data_dir)
    handler._send_json(hb_data if hb_data else {"status": "unknown"})


def handle_alerts(handler):
    """GET /api/alerts — 告警信息"""
    alerts = get_recent_alerts(handler.data_dir, limit=50)
    handler._send_json({"alerts": alerts})


def handle_config(handler):
    """GET /api/config — 查看总线配置（脱敏）"""
    from lib.adapters.config.config_admin import _redact_api_token

    config_path = f"{handler.data_dir}/config.json"
    config = json_read(config_path, {})
    safe = _redact_api_token({k: v for k, v in config.items() if k != "token"})
    handler._send_json(safe)


def _extract_repo_name(fname: str) -> str:
    """从文件名提取仓库名: review-mailbus-20260526.md → mailbus
    旧格式 review-<commit_prefix>-<date>.md → 未知项目"""
    parts = fname.replace(".md", "").split("-")
    if len(parts) >= 3 and parts[0] == "review":
        repo_parts = []
        for p in parts[1:]:
            # 纯数字且>=8位 → 日期戳，停止
            if p.isdigit() and len(p) >= 8:
                break
            # 短 hex（commit hash 前缀）→ 旧格式，返回未知
            if len(p) <= 8 and all(c in "0123456789abcdef" for c in p.lower()):
                return "未知项目（旧报告）"
            repo_parts.append(p)
        if repo_parts:
            return "-".join(repo_parts)
    return "未知项目（旧报告）"


def handle_code_reviews(handler):
    """GET /api/reviews — 返回代码审查报告列表"""
    reports_dir = os.path.join(handler.data_dir, "reports")
    reports = []
    if os.path.isdir(reports_dir):
        for fname in sorted(os.listdir(reports_dir), reverse=True):
            if fname.endswith(".md"):
                fpath = os.path.join(reports_dir, fname)
                try:
                    size = os.path.getsize(fpath)
                    mtime = os.path.getmtime(fpath)
                    import datetime
                    mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    preview = ""
                    with open(fpath, encoding="utf-8") as f:
                        preview = f.read()[:300]
                    repo = _extract_repo_name(fname)
                    reports.append({"file": fname, "repo": repo, "size": size,
                                    "time": mtime_str, "content": preview})
                except Exception:
                    pass
    handler._send_json({"reports": reports, "count": len(reports)})


def handle_code_reviews_projects(handler):
    """GET /api/reviews/projects — 按项目分组的代码审查报告"""
    reports_dir = os.path.join(handler.data_dir, "reports")
    projects = {}
    if os.path.isdir(reports_dir):
        for fname in sorted(os.listdir(reports_dir), reverse=True):
            if fname.endswith(".md"):
                fpath = os.path.join(reports_dir, fname)
                try:
                    repo = _extract_repo_name(fname)
                    mtime = os.path.getmtime(fpath)
                    import datetime
                    mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    projects.setdefault(repo, []).append({
                        "file": fname,
                        "time": mtime_str,
                        "size": os.path.getsize(fpath),
                    })
                except Exception:
                    pass
    for repo in projects:
        projects[repo] = projects[repo][:10]
    handler._send_json({"projects": projects, "count": len(projects)})


def handle_code_reviews_detail(handler, fname: str):
    """GET /api/reviews/<file> — 返回单份代码审查报告"""
    from lib.api.security import safe_report_path

    fpath = safe_report_path(handler.data_dir, "reports", fname)
    if not fpath or not fname.endswith(".md"):
        handler._send_json({"error": "not found"}, 404)
        return
    try:
        with open(fpath, encoding="utf-8") as f:
            content = f.read()
        # 尝试用 markdown 渲染
        try:
            import markdown
            html = markdown.markdown(content, extensions=["fenced_code", "codehilite"])
        except ImportError:
            html = f"<pre>{content}</pre>"
        handler._send_json({"file": fname, "html": html, "raw": content})
    except Exception as e:
        handler._send_json({"error": str(e)}, 500)


def handle_reports(handler):
    """GET /api/reports — 获取错误报告"""
    import glob
    try:
        errors_dir = os.path.join(handler.data_dir, "errors")
        reports = []
        if os.path.isdir(errors_dir):
            for fpath in sorted(glob.glob(f"{errors_dir}/*.jsonl"), reverse=True)[:7]:
                try:
                    with open(fpath, encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    fname = os.path.basename(fpath)
                    entries = []
                    for line in lines[-20:]:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
                    reports.append({"file": fname, "count": len(lines), "recent": entries})
                except (OSError, IOError):
                    pass
        handler._send_json({"reports": reports})
    except Exception as e:
        handler._send_json({"reports": [], "error": str(e)}, 500)


def handle_harness_report(handler, sha: str):
    """GET /api/harness-reports/<sha> — 读取 code-review-report-v1 JSON（只读）"""
    from lib.application.harness.report_api import (
        harness_report_summary,
        load_harness_report,
        normalize_commit_sha,
    )

    norm = normalize_commit_sha(sha)
    if not norm:
        handler._send_json({"error": "invalid_sha"}, 400)
        return
    report = load_harness_report(handler.data_dir, norm)
    if not report:
        handler._send_json({"error": "not_found", "commit_sha": norm}, 404)
        return
    handler._send_json({
        "commit_sha": report.get("commit_sha"),
        "summary": harness_report_summary(report),
        "report": report,
    })


def handle_report_content(handler, fname: str):
    """GET /api/report-content/<file> — 返回巡检报告内容"""
    from urllib.parse import unquote
    from lib.api.security import safe_report_path

    fname = unquote(fname)
    for subdir in ["patrol_reports", "reports", "reports/daily"]:
        fpath = safe_report_path(handler.data_dir, subdir, fname)
        if fpath:
            try:
                with open(fpath, encoding="utf-8") as f:
                    content = f.read()
                handler._send_json({"file": os.path.basename(fname), "content": content})
                return
            except Exception as e:
                handler._send_json({"error": str(e)}, 500)
                return
    handler._send_json({"error": "not_found"}, 404)


def handle_patrol_reports(handler):
    """GET /api/patrol-reports — 获取巡检日报列表"""
    import glob
    reports_dir = os.path.join(handler.data_dir, "patrol_reports")
    reports = []
    if os.path.isdir(reports_dir):
        for fpath in sorted(glob.glob(f"{reports_dir}/*.md"), reverse=True)[:20]:
            try:
                fname = os.path.basename(fpath)
                mtime = os.path.getmtime(fpath)
                import datetime
                date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                with open(fpath, encoding="utf-8") as f:
                    content = f.read()
                # 取前200字做摘要
                summary = content[:300].strip()
                reports.append({
                    "file": fname,
                    "date": date_str,
                    "created_at": date_str,
                    "summary": summary,
                    "content": content[:500],
                })
            except (OSError, IOError):
                pass
    handler._send_json({"reports": reports})


def handle_stats(handler):
    """GET /api/stats — 消息统计/报表

    聚合：消息总量、任务状态分布、Agent 排行、响应时间、趋势。
    """
    from lib.infra.utils import resolve_paths, _now_iso
    from lib.domain.models import Inbox
    from lib.application.orchestration.tracker import TaskTracker
    from datetime import datetime, timezone, timedelta

    paths = resolve_paths(handler.data_dir)
    tracker = TaskTracker(handler.data_dir)

    # ── 1. 逐 Agent 统计 ──
    agent_stats = {}
    total_messages = 0
    status_distribution = {}
    now = now_dt()

    for name in handler.agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        raw = json_read(inbox_file, [])
        if isinstance(raw, list):
            msgs = raw
        else:
            msgs = raw.get("messages", []) if raw else []
        total_messages += len(msgs)

        # 状态分布
        statuses = {"pending": 0, "pushed": 0, "acknowledged": 0,
                     "processing": 0, "done": 0, "failed": 0, "others": 0}
        for m in msgs:
            s = m.get("state", "") or m.get("status", "")
            if s in statuses:
                statuses[s] += 1
            else:
                statuses["others"] += 1
            status_distribution[s] = status_distribution.get(s, 0) + 1

        # 响应时间统计（从 created_at 到 acknowledged_at）
        response_times = []
        for m in msgs:
            created = m.get("created_at", "")
            acked = m.get("acknowledged_at", "")
            if created and acked and m.get("state") in ("done", "closed"):
                try:
                    t1 = datetime.fromisoformat(created)
                    t2 = datetime.fromisoformat(acked)
                    delta = (t2 - t1).total_seconds()
                    if delta > 0:
                        response_times.append(delta)
                except (ValueError, TypeError):
                    pass

        avg_response = sum(response_times) / len(response_times) if response_times else 0
        max_response = max(response_times) if response_times else 0

        agent_stats[name] = {
            "total": len(msgs),
            "statuses": statuses,
            "avg_response_seconds": round(avg_response, 1),
            "max_response_seconds": round(max_response, 1),
            "type": handler.agents[name].get("type", "?"),
            "role": handler.agents[name].get("role", ""),
        }

    # ── Token 估算（任务数 × 平均响应 × 100 tokens/s × 3 倍系数）──
    token_estimates = {}
    model_cost_cny = {
        "deepseek-chat": 7.3, "deepseek-flash": 2.0, "qwen-max": 14.6,
        "zhipu-4": 10.9, "default": 7.3,
    }
    for name, st in agent_stats.items():
        done_count = st["statuses"].get("done", 0) + st["statuses"].get("processing", 0)
        avg_rsp = st["avg_response_seconds"] or 30.0
        est_tokens = int(max(done_count, st["total"] // 4) * avg_rsp * 100 * 3)
        agent_cfg = handler.agents.get(name, {})
        models = agent_cfg.get("models") or ["deepseek-chat"]
        model = models[0] if models else "deepseek-chat"
        cost_per_m = model_cost_cny.get(model, model_cost_cny["default"])
        token_estimates[name] = {
            "estimated_tokens": est_tokens,
            "model": model,
            "cost_cny": round(est_tokens / 1_000_000 * cost_per_m, 4),
            "basis": "tasks×avg_response×100×3",
        }
    total_tokens = sum(v["estimated_tokens"] for v in token_estimates.values()) or 1

    # ── 2. 任务追踪统计 ──
    tasks = tracker.list_all()
    task_statuses = {"pending": 0, "running": 0, "success": 0,
                     "failed": 0, "timeout": 0, "cancelled": 0}
    for t in tasks:
        s = t.get("status", "")
        task_statuses[s] = task_statuses.get(s, 0) + 1

    # ── 3. 趋势（最近7天每天的消息量） ──
    trend = {}
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        trend[day] = 0
    for name in handler.agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        raw2 = json_read(inbox_file, [])
        msgs2 = raw2 if isinstance(raw2, list) else (raw2.get("messages", []) if raw2 else [])
        for m in msgs2:
            created = m.get("created_at", "")
            try:
                d = datetime.fromisoformat(created).strftime("%Y-%m-%d")
                if d in trend:
                    trend[d] += 1
            except (ValueError, TypeError):
                pass

    handler._send_json({
        "total_messages": total_messages,
        "agent_stats": agent_stats,
        "token_estimates": token_estimates,
        "total_estimated_tokens": total_tokens,
        "status_distribution": status_distribution,
        "task_statuses": task_statuses,
        "trend": trend,
        "timestamp": _now_iso(),
        "agent_count": len(handler.agents),
    })


def handle_search(handler):
    """GET /api/search — 消息 + 目录（外部工具）检索"""
    from urllib.parse import urlparse, parse_qs
    from lib.adapters.ops.search import search
    from lib.adapters.ops.catalog_search import search_catalog, search_all, index_catalog

    qs = parse_qs(urlparse(handler.path).query)
    query = qs.get("q", qs.get("query", [""]))[0]
    from_agent = qs.get("from", [""])[0]
    to_agent = qs.get("to", [""])[0]
    msg_type = qs.get("type", [""])[0]
    status = qs.get("status", [""])[0]
    scope = qs.get("scope", ["all"])[0]
    try:
        limit = int(qs.get("limit", ["20"])[0])
    except (ValueError, TypeError):
        limit = 20

    if scope in ("all", "catalog"):
        index_catalog(handler.data_dir, handler.agents)

    if scope == "all":
        if query:
            bundle = search_all(handler.data_dir, query_str=query, limit=limit, agents=handler.agents)
            handler._send_json({
                "query": query,
                "scope": "all",
                "total": len(bundle["messages"]) + len(bundle["catalog"]),
                "messages": bundle["messages"],
                "catalog": bundle["catalog"],
                "results": bundle["messages"],
            })
        else:
            msgs = search(
                handler.data_dir, query_str="", from_agent=from_agent,
                to_agent=to_agent, msg_type=msg_type, status=status, limit=limit,
            )
            cats = search_catalog(handler.data_dir, query_str="", limit=limit)
            handler._send_json({
                "query": query,
                "scope": "all",
                "total": len(msgs) + len(cats),
                "messages": msgs,
                "catalog": cats,
                "results": msgs,
            })
        return

    if scope == "catalog":
        results = search_catalog(handler.data_dir, query_str=query, limit=limit)
        handler._send_json({
            "query": query,
            "scope": "catalog",
            "total": len(results),
            "catalog": results,
            "results": results,
        })
        return

    results = search(
        handler.data_dir, query_str=query, from_agent=from_agent,
        to_agent=to_agent, msg_type=msg_type, status=status, limit=limit,
    )
    handler._send_json({"query": query, "scope": "messages", "total": len(results), "results": results})


def handle_external_tools(handler):
    """GET /api/external-tools — 外部工具注册表与 agent 配对"""
    from lib.adapters.ops.catalog_search import list_external_tools_summary
    handler._send_json(list_external_tools_summary(handler.data_dir))


def handle_templates(handler):
    """GET /api/templates — agent 类型模板"""
    handler._send_json(handler.agent_types)


def handle_agent_profile(handler, agent: str):
    """GET /api/agent-profile/<agent> — agent 详细信息（含身份/人设/技能）"""
    cfg = handler.agents.get(agent)
    if not cfg:
        handler._send_json({"error": "not found"}, 404)
        return

    profile = {
        "name": agent,
        "config": cfg,
        "identity": None,
        "soul": None,
        "skills": [],
    }

    identity_used = None
    # 从 profile_paths 读取身份/人设/技能（解析 Docker /mailbus/ 路径）
    paths_cfg = cfg.get("profile_paths", {}) or {}
    for identity_path in identity_candidates(handler.data_dir, agent, paths_cfg.get("identity", "")):
        if identity_path and os.path.isfile(identity_path):
            try:
                with open(identity_path, "r", encoding="utf-8", errors="replace") as f:
                    profile["identity"] = f.read(12000)
                identity_used = identity_path
                break
            except Exception:
                pass

    soul_path = resolve_mailbus_path(handler.data_dir, paths_cfg.get("soul", ""))
    if not soul_path or not os.path.isfile(soul_path):
        from lib.infra.constants import MAILBUS_IDENTITIES_ROOT_STR

        for alt in (
            os.path.join(MAILBUS_IDENTITIES_ROOT_STR, agent, "SOUL.md"),
            os.path.join(MAILBUS_IDENTITIES_ROOT_STR, f"{agent}-soul.md"),
            os.path.join(MAILBUS_IDENTITIES_ROOT_STR, f"{agent}.md"),
        ):
            if os.path.isfile(alt):
                soul_path = alt
                break
    soul_ok = bool(soul_path and os.path.isfile(soul_path))
    if soul_ok:
        try:
            with open(soul_path, "r", encoding="utf-8", errors="replace") as f:
                profile["soul"] = f.read(4000)
        except Exception:
            soul_ok = False

    skill_dirs = paths_cfg.get("skills_dirs", []) or []
    all_skills = set()
    for sd in skill_dirs:
        sd_resolved = resolve_mailbus_path(handler.data_dir, sd) if str(sd).startswith("/") else sd
        if os.path.isdir(sd_resolved):
            try:
                for fname in sorted(os.listdir(sd_resolved)):
                    if fname.endswith((".md", ".py", ".sh", ".txt")):
                        all_skills.add(fname.rsplit(".", 1)[0])
            except Exception:
                pass
    profile["skills"] = sorted(all_skills)

    # 结构化名片（store/agents/json/profile-cards.json）
    cards_path = os.path.join(handler.data_dir, "agents", "json", "profile-cards.json")
    cards_data = json_read(cards_path, {})
    card = (cards_data.get("cards") or {}).get(agent, {})
    if card:
        profile["card"] = card

    # inbox 统计
    inbox_paths = resolve_paths(handler.data_dir)
    inbox_file = f"{inbox_paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {})
    # v4.0: 兼容 inbox.json dict→list 格式迁移
    if isinstance(data, list):
        data = {"agent": agent, "has_unread": True, "messages": data, "since": _now_iso()}
    profile["messages"] = len(data.get("messages", [])) if data else 0
    profile["unread"] = 0
    if data:
        inbox = Inbox.from_dict(data)
        for m in inbox.messages:
            if inbox.msg_field(m, "status") == "pending":
                profile["unread"] += 1

    # 心跳
    hb_data = load_heartbeat(handler.data_dir)
    profile["heartbeat"] = (hb_data.get("agents", {}) or {}).get(agent, {}) if hb_data else {}

    # 头像：web/public 与 docs/avatars 双根
    from lib.infra.constants import MAILBUS_DOCS_ROOT_STR, MAILBUS_ROOT

    avatar_roots = [
        os.path.join(str(MAILBUS_ROOT), "web", "public", "avatars"),
        os.path.join(MAILBUS_DOCS_ROOT_STR, "avatars"),
    ]

    def _first(*names: str) -> str:
        for root in avatar_roots:
            for name in names:
                if os.path.isfile(os.path.join(root, name)):
                    return f"avatars/{name}"
        return f"avatars/{names[0]}"

    profile["avatar_url"] = _first(f"{agent}_portrait.png", f"{agent}_portrait.svg")
    profile["avatar_animated"] = _first(f"{agent}_animated.webp", f"{agent}_animated.svg")
    if not profile.get("avatar_animated"):
        profile["avatar_animated"] = profile["avatar_url"]

    profile["paths"] = {
        "identity": identity_used,
        "identity_ok": bool(identity_used),
        "soul": soul_path if soul_ok else None,
        "soul_ok": soul_ok,
        "cards_ok": bool(card),
        "cards_file": cards_path if os.path.isfile(cards_path) else None,
        "configured_identity": paths_cfg.get("identity") or None,
    }

    handler._send_json(profile)


def _probe_http_url(url: str, timeout: float = 2.0) -> dict:
    """短探测浏览器入口可达性（不跟随到外站登录页失败也算可达）。"""
    import urllib.error
    import urllib.request

    out = {"ok": False, "status": None, "error": None, "probed_url": url}
    if not url:
        out["error"] = "empty_url"
        return out
    # 容器内 127.0.0.1 指容器自身；宿主 UI 需走 host.docker.internal
    probed = url
    try:
        in_docker = os.path.exists("/.dockerenv") or os.environ.get("MAILBUS_IN_DOCKER") == "1"
        if in_docker and "127.0.0.1" in url:
            probed = url.replace("127.0.0.1", "host.docker.internal")
            out["probed_url"] = probed
    except Exception:
        probed = url
    try:
        req = urllib.request.Request(probed, method="GET", headers={"User-Agent": "mailbus-access-probe"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out["status"] = int(getattr(resp, "status", 200) or 200)
            out["ok"] = 200 <= out["status"] < 500
            return out
    except urllib.error.HTTPError as exc:
        out["status"] = int(exc.code)
        # 401/403 说明服务活着，只是鉴权
        out["ok"] = 400 <= exc.code < 500
        out["error"] = f"HTTP {exc.code}"
        return out
    except Exception as exc:
        out["error"] = str(exc)[:200]
        return out


def handle_ping(handler, agent: str):
    """GET /api/ping/<agent> — 在线状态 + 浏览器/终端访问校验。"""
    from lib.adapters.ops.heartbeat import is_online

    if agent not in handler.agents:
        handler._send_json({"error": "not found", "agent": agent}, 404)
        return

    cfg = handler.agents.get(agent) or {}
    meta = _agent_launch_meta(handler, agent, cfg)
    online = is_online(handler.data_dir, agent)

    browser = {
        "configured": bool(meta.get("has_browser")),
        "url": meta.get("launch_url") or "",
        "ok": False,
        "status": None,
        "error": None,
    }
    if browser["configured"] and browser["url"]:
        probe = _probe_http_url(browser["url"])
        browser.update(probe)
    elif browser["configured"]:
        browser["error"] = "missing_launch_url"
    else:
        browser["error"] = "browser_not_configured"

    script_path = _resolve_launch_script_path()
    via_api = bool(meta.get("launch_via_api"))
    cli_ok = via_api or bool(script_path and os.path.isfile(script_path))
    cli = {
        "configured": True,
        "ok": cli_ok,
        "via_api": via_api,
        "script": script_path if script_path and os.path.isfile(script_path) else "",
        "error": None if cli_ok else "launch_script_missing",
    }

    paths_cfg = cfg.get("profile_paths", {}) or {}
    identity_used = None
    for identity_path in identity_candidates(handler.data_dir, agent, paths_cfg.get("identity", "")):
        if identity_path and os.path.isfile(identity_path):
            identity_used = identity_path
            break
    cards_path = os.path.join(handler.data_dir, "agents", "json", "profile-cards.json")
    cards_data = json_read(cards_path, {})
    has_card = bool((cards_data.get("cards") or {}).get(agent))

    handler._send_json({
        "agent": agent,
        "online": online,
        "browser": browser,
        "cli": cli,
        "launch": meta,
        "paths": {
            "identity": identity_used,
            "identity_ok": bool(identity_used),
            "soul": None,
            "soul_ok": False,
            "cards_ok": has_card,
            "configured_identity": paths_cfg.get("identity") or None,
        },
    })


def handle_avatars_manifest(handler):
    """GET /api/avatars/manifest — 13 人静+动齐套门禁状态。"""
    from lib.infra.constants import MAILBUS_DOCS_ROOT_STR, MAILBUS_ROOT

    roster = [
        "ziyan",
        "lingzhao",
        "lingjin",
        "lingxi",
        "xiaoqi",
        "yige",
        "lingxiao",
        "dali",
        "lingjian",
        "lingyan",
        "lingxun",
        "lingzhang",
        "lingtuo",
    ]
    roots = [
        os.path.join(MAILBUS_DOCS_ROOT_STR, "avatars"),
        os.path.join(str(MAILBUS_ROOT), "web", "public", "avatars"),
    ]
    pairs = []
    ok_n = 0
    for aid in roster:
        still = any(os.path.isfile(os.path.join(r, f"{aid}_portrait.png")) for r in roots)
        motion = any(os.path.isfile(os.path.join(r, f"{aid}_animated.webp")) for r in roots)
        ready = still and motion
        if ready:
            ok_n += 1
        pairs.append({"id": aid, "portrait": still, "animated": motion, "ready": ready})
    handler._send_json(
        {
            "expected": len(roster),
            "count": ok_n,
            "complete": ok_n >= len(roster),
            "pairs": pairs,
            "gate": "all_13_static_plus_animated_same_identity",
        }
    )


def handle_agent_recruit(handler):
    """POST /api/agents/recruit — 提交新员工需求，派发给灵昭生成 AI 员工方案。"""
    body = handler._read_post_body()
    platform = (body.get("platform") or "").strip()
    display_name = (body.get("name") or body.get("display_name") or "").strip()
    if not display_name:
        handler._send_json({"error": "缺少 name"}, 400)
        return
    gender = body.get("gender", "")
    mbti = body.get("mbti", "")
    zodiac = body.get("zodiac", "")
    age = body.get("age", "")
    role = body.get("role", "")
    personality = body.get("personality", "")
    work_req = body.get("work_requirements") or body.get("work", "")

    lines = [
        "【Dashboard 新员工招募请求】",
        f"姓名/代号: {display_name}",
    ]
    if platform:
        lines.append(f"Agent 平台: {platform}")
    if gender:
        lines.append(f"性别: {gender}")
    if age:
        lines.append(f"年龄: {age}")
    if zodiac:
        lines.append(f"星座: {zodiac}")
    if mbti:
        lines.append(f"MBTI: {mbti}")
    if role:
        lines.append(f"角色定位: {role}")
    if personality:
        lines.append(f"性格要求: {personality}")
    if work_req:
        lines.append(f"工作要求: {work_req}")
    lines.extend([
        "",
        "请灵昭输出：",
        "1. agent id 建议（英文 snake_case）",
        "2. config.json agents 条目草案（含 type/profile_paths/launch）",
        "3. identities/{id}.md 完整人设（含年龄/星座/MBTI/角色/核心特质/职责）",
        "4. 是否需要 ComfyUI 生成肖像（性别对应的动漫 3D 真人风）",
    ])
    content = "\n".join(lines)

    to = "lingzhao"
    if to not in handler.agents:
        handler._send_json({"error": "lingzhao 未注册"}, 503)
        return
    from lib.infra.utils import build_message
    msg_dict = build_message("dashboard", to, content, "task", "high").to_dict()
    msg_dict["subject"] = f"招募新员工: {display_name}"
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{to}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": to, "has_unread": False, "messages": [], "since": _now_iso()})
    if isinstance(inbox_data, list):
        inbox_data = {"agent": to, "has_unread": True, "messages": inbox_data, "since": _now_iso()}
    from lib.domain.models import Inbox
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg_dict)
    json_write(inbox_file, inbox.to_dict())
    try:
        from lib.application.push.pusher import push_messages, resolve_cli_chain

        agent_cfg = handler.agents.get(to, {})
        cli_chain = resolve_cli_chain(agent_cfg, handler.agent_types)
        if cli_chain:
            push_messages(handler.data_dir, to, [msg_dict], cli_cmd=[c[0] for c in cli_chain], auto_ack=False)
    except Exception as exc:
        import logging
        logging.getLogger("mailbus.api").warning("recruit push failed for %s: %s", to, exc)
        try:
            from ..utils import log_error
            log_error(paths["errors"], msg_dict["id"], to, f"recruit_push: {exc}")
        except Exception:
            pass
        handler._send_json({
            "status": "partial",
            "msg_id": msg_dict["id"],
            "to": to,
            "warning": f"inbox written but push failed: {exc}",
        })
        return
    handler._send_json({"status": "ok", "msg_id": msg_dict["id"], "to": to})


def _get_gateway_token() -> str:
    """读取 OpenClaw gateway token（与 Docker entrypoint 保持一致）"""
    env_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if env_token:
        return env_token

    candidates = [
        str(MAILBUS_ROOT.parent / "openclaw_space" / "data" / ".openclaw" / "openclaw.json"),
        os.path.expanduser("~/.openclaw-data/openclaw.json"),
        os.path.expanduser("~/.openclaw/openclaw.json"),
    ]
    for oc_path in candidates:
        try:
            if os.path.isfile(oc_path):
                with open(oc_path) as f:
                    oc = json.load(f)
                gw = oc.get("gateway", {})
                auth = gw.get("auth", {})
                if auth.get("mode") == "token":
                    token = auth.get("token", "")
                    if token:
                        return token
        except Exception:
            pass
    return "ziyan-team"


def _with_gateway_token(url: str, token: str) -> str:
    """把 URL 里的 token 参数统一替换成当前 gateway token"""
    if not url or not token:
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["token"] = [token]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _get_launch_url(handler, agent_name: str) -> str:
    """从 agent 配置中提取浏览器启动 URL（含 gateway token）"""
    cfg = handler.agents.get(agent_name, {})
    launch = cfg.get("launch", {})
    if not launch:
        return ""
    # 合并模板 + agent 覆盖（与 launch-agent.sh 逻辑一致）
    tmpl_name = launch.get("template", "")
    tmpl = handler.agent_types.get("launch_templates", {}).get(tmpl_name, {})
    browser_cfg = dict(tmpl.get("browser", {}))
    browser_cfg.update(launch.get("browser", {}))
    url = browser_cfg.get("url", "")
    tmpl_name = launch.get("template", "")
    if tmpl_name == "openclaw_gateway" or cfg.get("type") == "openclaw":
        from lib.adapters.frameworks import OpenClawAdapter

        port = OpenClawAdapter.resolve_gateway_port(agent_name, browser_cfg)
    else:
        from lib.adapters.config.launch_ports import resolve_port

        port = resolve_port(agent_name, cfg, browser_cfg)
    if url and port is not None:
        url = url.replace("{port}", str(port))
    elif url and "{port}" in url:
        return ""
    if url:
        url = url.replace("{agent}", agent_name)
    # 仅 OpenClaw gateway 需要 token，Hermes/Cline 等不要误加
    if tmpl_name == "openclaw_gateway" or cfg.get("type") == "openclaw":
        token = _get_gateway_token()
        url = _with_gateway_token(url, token)
    return url


def handle_list_launchable(handler):
    """GET /api/launch — 列出可启动的 agent（含启动模式、has_browser、launch_url 等信息）"""
    agents, _ = _reload_store_config(handler)
    result = {}
    for name, cfg in agents.items():
        atype = cfg.get("type", "none")
        meta = _agent_launch_meta(handler, name, cfg)
        result[name] = {
            "name": cfg.get("name", name),
            "type": atype,
            "models": cfg.get("models", []),
            **meta,
        }
    handler._send_json({"agents": result})


def handle_launch(handler):
    """POST /api/launch — 通过 launch-agent.sh 启动 agent"""
    body = handler._read_post_body()
    agent = body.get("agent", "")
    mode = body.get("mode", "browser")
    if mode not in ("browser", "cli", "desktop"):
        handler._send_json({"error": f"invalid mode: {mode}"}, 400)
        return

    agents, _ = _reload_store_config(handler)
    if not agent or agent not in agents:
        handler._send_json({"error": f"agent '{agent}' not found"}, 404)
        return

    in_container = _running_in_mailbus_container()
    agent_type = agents[agent].get("type", "")
    meta = _agent_launch_meta(handler, agent, agents[agent])
    launch_via_api = bool(meta.get("launch_via_api"))

    # ── 容器内：Claude Code / Codex 浏览器直返 URL（不走脚本，避免 WSL/ttyd 超时）──
    if in_container and mode == "browser" and launch_via_api:
        url = _resolve_agent_browser_url(handler, agent)
        if url:
            # 快速探测一次确认可达
            probe = _probe_http_url(url)
            if probe.get("ok"):
                handler._send_json({
                    "status": "ok",
                    "agent": agent,
                    "message": f"Launched {agent} (browser)",
                    "url": url,
                })
                return
        # probe 失败也返回 URL，前端可尝试打开
        handler._send_json({
            "status": "ok",
            "agent": agent,
            "message": f"Launched {agent} (browser · unchecked)",
            "url": url or "",
        })
        return

    # ── 容器内：Docker 类 agent CLI 直接 docker exec（docker.sock 已挂载，不用走 WSL）──
    if in_container and mode == "cli":
        atype = agents[agent].get("type", "")
        if atype in ("opencode", "codex", "openclaw", "hermes", "hermes_profile"):
            from lib.adapters.frameworks.registry import resolve_container, get_adapter

            adapter = get_adapter(atype)
            container = resolve_container(agents[agent], agent,
                                          adapter.container_service if adapter else "") if adapter else ""
            if container:
                # 构建交互 CLI 命令，入队给 watchdog 在 WSL 弹出终端
                profile = agents[agent].get("profile", agent)
                if atype == "hermes_profile":
                    cmd = f'docker exec -it {container} hermes -p {profile} chat --yolo'
                elif atype == "hermes":
                    cmd = f'docker exec -it {container} hermes -p {profile} chat'
                elif atype == "openclaw":
                    cmd = f'docker exec -it {container} openclaw tui'
                elif atype == "codex":
                    cmd = f'docker exec -it {container} codex'
                elif atype in ("opencode",):
                    cmd = f'docker exec -it {container} bash -c "cd /workspace/opencode && opencode"'
                else:
                    # opencode / codex: 仅验证容器可达
                    check = subprocess.run(
                        ["docker", "exec", container, "echo", "ok"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if check.returncode == 0:
                        handler._send_json({
                            "status": "ok",
                            "agent": agent,
                            "message": f"Launched {agent} (cli · container ready)",
                        })
                        return
                    err_detail = (check.stderr or check.stdout or f"exit {check.returncode}").strip()
                    handler._send_json({
                        "status": "error",
                        "agent": agent,
                        "error": err_detail,
                    }, 500)
                    return

                # hermes_profile / hermes / openclaw：入队到 watchdog
                from lib.adapters.frameworks.claude_launch import enqueue_launch_queue
                if enqueue_launch_queue(cmd, agent, mode="interactive"):
                    handler._send_json({
                        "status": "ok",
                        "agent": agent,
                        "message": f"Launched {agent} (cli · queued)",
                    })
                    return
                handler._send_json({
                    "status": "error",
                    "agent": agent,
                    "error": "launch queue write failed",
                }, 500)
                return
            # 无 container 则落到脚本兜底

    script_path = _resolve_launch_script_path()

    if mode == "desktop" and not in_container:
        from lib.adapters.frameworks.desktop_launch import agent_has_desktop, launch_desktop

        if not agent_has_desktop(agents[agent], handler.agent_types):
            handler._send_json({"error": f"agent '{agent}' has no desktop launch configured"}, 400)
            return
        if sys.platform == "win32":
            try:
                info = launch_desktop(agent, handler.data_dir)
                handler._send_json({
                    "status": "ok",
                    "agent": agent,
                    "message": f"Launched {agent} (desktop)",
                    **info,
                })
                return
            except Exception as e:
                handler._send_json({"status": "error", "agent": agent, "error": str(e)}, 500)
                return

    if not in_container and agent_type == "claude_code":
        if mode == "browser":
            from lib.adapters.frameworks.claude_browser_launch import launch_claude_browser

            try:
                info = launch_claude_browser(agent, handler.data_dir)
                handler._send_json({
                    "status": "ok",
                    "agent": agent,
                    "message": f"Launched {agent} (browser)",
                    **info,
                })
                return
            except Exception as e:
                handler._send_json({"status": "error", "agent": agent, "error": str(e)}, 500)
                return

        if mode == "cli":
            from lib.adapters.frameworks.claude_launch import launch_claude_cli

            try:
                info = launch_claude_cli(agent, handler.data_dir)
                handler._send_json({
                    "status": "ok",
                    "agent": agent,
                    "message": f"Launched {agent} (cli)",
                    **info,
                })
                return
            except Exception as e:
                handler._send_json({"status": "error", "agent": agent, "error": str(e)}, 500)
                return

    if not script_path:
        handler._send_json({"error": "launch script not found"}, 500)
        return

    try:
        result = _run_launch_script(script_path, agent, mode)
        if result.returncode == 0:
            payload = {
                "status": "ok",
                "agent": agent,
                "message": f"Launched {agent} ({mode})",
            }
            if mode == "browser":
                url = _parse_launch_stdout_url(result.stdout) or _resolve_agent_browser_url(handler, agent)
                if url:
                    payload["url"] = url
            handler._send_json(payload)
        else:
            err = (result.stderr or "").strip() or (result.stdout or "").strip() or f"exit {result.returncode}"
            handler._send_json({"status": "error", "agent": agent, "error": err}, 500)
    except subprocess.TimeoutExpired:
        handler._send_json({"status": "timeout", "agent": agent}, 500)
    except Exception as e:
        handler._send_json({"status": "error", "error": str(e)}, 500)


def _launch_agentmemory(handler):
    """重启 AgentMemory 服务（Docker compose 优先）。"""
    compose_dir = os.environ.get(
        "MAILBUS_COMPOSE_DIR",
        str(MAILBUS_ROOT / "docker-agents"),
    )
    compose_file = os.path.join(compose_dir, "docker-compose.yml")
    if not os.path.isfile(compose_file):
        handler._send_json({"error": f"compose 不存在: {compose_file}"}, 404)
        return
    try:
        if os.path.exists("/var/run/docker.sock"):
            r = subprocess.run(
                ["docker", "compose", "-f", compose_file, "restart", "iii-engine", "agentmemory"],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0:
                handler._send_json({
                    "agent": "agentmemory",
                    "status": "error",
                    "detail": (r.stderr or r.stdout or "docker compose failed")[:300],
                }, 500)
                return
        else:
            handler._send_json({"error": "docker.sock 不可用，无法重启 AgentMemory"}, 503)
            return
        for i in range(60):
            time.sleep(1)
            result = _check_agentmemory()
            if result.get("status") == "healthy":
                handler._send_json({
                    "agent": "agentmemory",
                    "status": "healthy",
                    "detail": f"重启成功（第{i + 1}秒响应）",
                })
                return
        handler._send_json({"agent": "agentmemory", "status": "timeout", "detail": "60秒内未就绪"})
    except subprocess.TimeoutExpired:
        handler._send_json({"agent": "agentmemory", "status": "timeout", "detail": "docker compose 超时"}, 504)
    except Exception as e:
        handler._send_json({"error": str(e)}, 500)


def _check_agentmemory():
    try:
        from urllib.request import urlopen
        import os
        base = os.environ.get("AGENTMEMORY_URL", "")
        if not base:
            base = "http://iii-engine:3111" if os.path.exists("/.dockerenv") else "http://127.0.0.1:3111"
        for ep in ("/agentmemory/health", "/health", "/"):
            try:
                resp = urlopen(f"{base.rstrip('/')}{ep}", timeout=5)
                if resp.getcode() in (200, 401, 404):
                    return {"status": "healthy", "endpoint": ep}
            except Exception:
                continue
        return {"status": "unreachable"}
    except Exception:
        return {"status": "unreachable"}


def handle_clinic_tools(handler):
    """GET /api/clinic/tools — mailbus 诊所工具列表"""
    from lib.adapters.ops.clinic_tools import list_clinic_tools
    handler._send_json({"tools": list_clinic_tools()})


def handle_clinic_jobs(handler):
    """GET /api/clinic/jobs — 调度任务状态（Dashboard 诊所）。"""
    from lib.adapters.ops.scheduler import get_scheduler_status

    handler._send_json(get_scheduler_status())


def handle_doctor(handler):
    """GET /api/doctor — 结构化诊断（Dashboard 诊所健康区）。"""
    from lib.adapters.ops.doctor_checks import run_doctor_checks

    try:
        handler._send_json(run_doctor_checks())
    except Exception as exc:
        handler._send_json({"ok": False, "error": str(exc)}, 500)


def handle_locale_errors(handler):
    """GET /api/locale/errors — W7e D21 驾驶舱错误码中文目录。"""
    from lib.domain.error_codes import ALL_STABLE_CODES
    from lib.adapters.locale.errors_zh import locale_catalog, stable_codes_covered

    catalog = locale_catalog()
    handler._send_json({
        "ok": True,
        "errors": catalog,
        "stable_codes": list(ALL_STABLE_CODES),
        "covered": stable_codes_covered(),
    })


def handle_clinic_run(handler):
    """POST /api/clinic/run — 执行诊所工具"""
    from lib.adapters.ops.clinic_tools import run_clinic_tool
    body = handler._read_post_body()
    tool_id = (body.get("tool_id") or "").strip()
    if not tool_id:
        handler._send_json({"ok": False, "error": "tool_id required"}, 400)
        return
    preset_index = int(body.get("preset_index") or 0)
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    result = run_clinic_tool(
        tool_id,
        preset_index=preset_index,
        params=params,
        data_dir=handler.data_dir,
    )
    status = 200 if result.get("ok") else 500
    if result.get("error") in ("unknown_tool",):
        status = 404
    handler._send_json(result, status)


def handle_dev_reload(handler):
    """POST /api/dev/reload — soft plugin reload + optional module reload."""
    body = handler._read_post_body() if handler.command == "POST" else {}
    want_modules = bool(body.get("modules")) or os.environ.get("MAILBUS_DEV_MODULE_RELOAD", "0") == "1"
    out: dict = {"status": "ok"}
    try:
        from lib.adapters.frameworks.entry_point_discovery import reload_framework_plugins
        from lib.adapters.integrations.entry_point_discovery import reload_integration_plugins
        from lib.infra.utils import json_read

        cfg = json_read(os.path.join(handler.data_dir, "config.json"), {})
        out["frameworks"] = reload_framework_plugins(data_dir=handler.data_dir, config=cfg)
        out["integrations"] = reload_integration_plugins(data_dir=handler.data_dir, config=cfg)
    except Exception as exc:
        out["plugins_error"] = str(exc)
    if want_modules:
        try:
            from lib.application.ops.module_reload import reload_mailbus_modules

            out["modules"] = reload_mailbus_modules()
        except Exception as exc:
            out["modules_error"] = str(exc)
    handler._send_json(out)


def handle_test_agents(handler):
    """GET /api/test-agents — 运行 test_agents.py 返回 JSON 报告。"""
    try:
        import subprocess
        import sys
        from lib.infra.constants import MAILBUS_ROOT

        script = str(MAILBUS_ROOT / "tools" / "test_agents.py")
        r = subprocess.run(
            [sys.executable, script, "--json", "--data-dir", handler.data_dir],
            capture_output=True, text=True, timeout=120,
            cwd=str(MAILBUS_ROOT),
        )
        if r.returncode == 0:
            import json as j
            handler._send_json(j.loads(r.stdout))
        else:
            handler._send_json({
                "ok": False,
                "error": r.stderr.strip()[:500] or r.stdout.strip()[:500],
                "returncode": r.returncode,
            })
    except Exception as exc:
        handler._send_json({"ok": False, "error": str(exc)})

