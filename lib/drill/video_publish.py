"""video_publish tool_live 演练 — dry_run / n8n 探测 / live。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List

from ..env_bootstrap import load_mailbus_env
from lib.adapters.integrations.external_tools import invoke_tool
from ..utils import json_read
from ..workflow.registry import get_gate_def, load_registry
from ..workflow.tool_exec import mark_tool_live_after_gate, run_tool_step, tool_live_enabled


class DrillError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(message or code)


def probe_n8n_webhook(url: str, *, timeout: float = 10.0) -> dict:
    if not url:
        return {"ok": False, "url": "", "detail": "N8N_PUBLISH_WEBHOOK_URL empty"}
    payload = {
        "task_id": "drill-probe",
        "content_id": "drill-probe",
        "platforms": ["douyin"],
        "assets": [],
    }
    try:
        from lib.adapters.integrations.n8n.wsl_bridge import post_json_with_wsl_fallback

        status, body = post_json_with_wsl_fallback(
            url,
            payload,
            {"Content-Type": "application/json"},
            timeout=int(timeout),
        )
        detail = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)[:300]
        return {"ok": 200 <= status < 300, "url": url, "status": status, "detail": detail}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "url": url, "detail": str(exc)}


def run_video_publish_drill(
    data_dir: str,
    *,
    mode: str = "dry",
    live: bool = False,
) -> dict:
    """返回 { ok, steps[], warnings[], mode }。"""
    load_mailbus_env()
    if mode == "check-n8n" or mode == "check_n8n":
        url = os.environ.get("N8N_PUBLISH_WEBHOOK_URL", "")
        probe = probe_n8n_webhook(url)
        return {
            "ok": probe.get("ok", False),
            "mode": "check-n8n",
            "steps": [{"id": "n8n_probe", "status": "pass" if probe.get("ok") else "fail", "detail": probe}],
            "warnings": [],
        }

    if live or mode == "live":
        mode = "live"
    else:
        mode = "dry"

    steps: List[dict] = []
    warnings: List[str] = []

    def step(sid: str, ok: bool, detail: str = "", extra: Any = None) -> None:
        steps.append({"id": sid, "status": "pass" if ok else "fail", "detail": detail, "extra": extra})
        if not ok:
            raise DrillError(sid, detail)

    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    wf_cfg = cfg.get("mailbus_workflow") or {}

    try:
        step("global_tool_live_off", not wf_cfg.get("tool_live"), "mailbus_workflow.tool_live must be false")
        step(
            "tool_live_gates",
            "publish_go" in (wf_cfg.get("tool_live_gates") or []),
            "publish_go in tool_live_gates",
        )

        reg = load_registry(data_dir)
        wf = (reg.get("workflows") or {}).get("video_publish") or {}
        gate = get_gate_def(wf, "publish_go") or {}
        on_ap = gate.get("on_approve") or {}
        step("registry_publish_go", bool(on_ap.get("tool_live")), "publish_go.on_approve.tool_live")

        task = {
            "task_id": "drill-video-publish-ui",
            "intent": "UI 演练：多平台发布",
            "extensions": {"ziyan": {"workflow": {"workflow_id": "video_publish", "gates": []}}},
        }
        step("pre_gate_dry", not tool_live_enabled(data_dir, task), "tool_live false before approve")

        mark_tool_live_after_gate(task, {}, gate)
        step("post_approve_live", tool_live_enabled(data_dir, task), "tool_live true after publish_go")

        dry = invoke_tool(
            data_dir,
            agent_id="mailbus",
            tool_id="webhook-multi-publish",
            inputs={
                "task_id": task["task_id"],
                "content_id": "drill-content-dry",
                "platforms": ["douyin", "bilibili"],
                "assets": [],
            },
            dry_run=True,
        )
        step("invoke_dry_run", bool(dry.get("dry_run")), "webhook-multi-publish dry_run", dry)

        task2 = json.loads(json.dumps(task))
        mark_tool_live_after_gate(task2, {}, gate)
        res = run_tool_step(
            data_dir,
            task2,
            "webhook-multi-publish",
            agent_id="mailbus",
            inputs={
                "task_id": task2["task_id"],
                "content_id": "drill-content-step",
                "platforms": ["douyin"],
                "assets": [],
            },
            dry_run=True,
        )
        step("run_tool_step_dry", bool(res.get("dry_run")), "run_tool_step dry_run")

        url = os.environ.get("N8N_PUBLISH_WEBHOOK_URL", "")
        if url:
            probe = probe_n8n_webhook(url, timeout=4.0 if mode == "dry" else 10.0)
            steps.append({
                "id": "n8n_probe",
                "status": "pass" if probe.get("ok") else "warn",
                "detail": probe.get("detail", ""),
                "extra": probe,
            })
            if not probe.get("ok"):
                warnings.append(
                    "n8n webhook 不可达或未注册 workflow — 导入 mailbus-multi-publish.workflow.json 并 Activate"
                )
        else:
            warnings.append(
                "N8N_PUBLISH_WEBHOOK_URL 未设置 — 先 python tools/mailbus.py docker start-n8n，再配置 webhook URL"
            )

        if mode == "live":
            if not url:
                step("live_requires_url", False, "N8N_PUBLISH_WEBHOOK_URL required")
            live_res = invoke_tool(
                data_dir,
                agent_id="mailbus",
                tool_id="webhook-multi-publish",
                inputs={
                    "task_id": task["task_id"],
                    "content_id": "drill-live-ui",
                    "platforms": ["douyin"],
                    "assets": [],
                },
                dry_run=False,
            )
            step(
                "live_invoke",
                live_res.get("ok") and not live_res.get("dry_run"),
                "live POST webhook-multi-publish",
                live_res,
            )

        return {"ok": True, "mode": mode, "steps": steps, "warnings": warnings}

    except DrillError as exc:
        return {
            "ok": False,
            "mode": mode,
            "steps": steps,
            "warnings": warnings,
            "error": exc.code,
            "message": exc.message,
        }

