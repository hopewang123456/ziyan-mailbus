"""mailbus 诊所 — agent / mailbus 总线诊断与修复工具注册表。"""
from __future__ import annotations

from lib.infra.clock import now_dt, now_ts, now_utc_dt
import os
import subprocess
import sys
import time
from typing import Any, Optional

from lib.infra.agent_demo import clinic_demo_agents
from lib.infra.constants import DEFAULT_API_BASE

MAIL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_DEMO_AGENTS = clinic_demo_agents() or ["agent-a", "agent-c", "agent-m"]


def _agent_options() -> list[str]:
    """从 store/config.json 读取 agents 名；缺失时回落到 demo 名单。"""
    import json

    cfg_path = os.path.join(MAIL_ROOT, "store", "config.json")
    try:
        if os.path.isfile(cfg_path):
            cfg = json.load(open(cfg_path, encoding="utf-8"))
            agents = list((cfg.get("agents") or {}).keys())
            if agents:
                return agents
    except (OSError, json.JSONDecodeError):
        pass
    return list(_DEMO_AGENTS)


_AGENT_OPTIONS = _agent_options()

# 仅 mailbus 总线与 agent 运维；不含 pipeline / V3 任务工具
CLINIC_TOOLS: list[dict[str, Any]] = [
    {
        "id": "check-token-status",
        "name": "Token / Scan 状态",
        "description": "scheduler 运行、scan 间隔、pending/processing 与 token 活动级别。",
        "category": "mailbus 总线",
        "readonly": True,
        "timeout": 30,
        "presets": [{"label": "检查", "args": []}],
    },
    {
        "id": "validate-scheduler",
        "name": "Scheduler 校验",
        "description": "验证内置 SchedulerHub：scan 任务、memory_bridge、pipeline_watchdog 等 job 状态。",
        "category": "mailbus 总线",
        "readonly": True,
        "timeout": 30,
        "presets": [{"label": "校验", "args": []}],
    },
    {
        "id": "diagnose-blockers",
        "name": "mailbus 卡点诊断",
        "description": "汇总 running 任务、stale chain、各 agent inbox pending/processing 积压。",
        "category": "mailbus 总线",
        "readonly": True,
        "timeout": 60,
        "presets": [{"label": "诊断", "args": []}],
    },
    {
        "id": "validate-agents-config",
        "name": "Agent 配置校验",
        "description": "检查 config.json 中各 agent 的 CLI 类型、profile、launch 模板是否一致。",
        "category": "Agent 配置",
        "readonly": True,
        "timeout": 60,
        "presets": [{"label": "校验全部", "args": []}],
    },
    {
        "id": "resolve-agent-cli",
        "name": "Agent CLI 解析",
        "description": "查看指定 agent 的 push / interactive 启动命令（adapter 层输出）。",
        "category": "Agent 配置",
        "readonly": True,
        "timeout": 30,
        "params": [
            {"name": "agent", "label": "Agent", "type": "select",
             "options": _AGENT_OPTIONS, "default": _AGENT_OPTIONS[0] if _AGENT_OPTIONS else ""},
            {"name": "mode", "label": "模式", "type": "select",
             "options": ["push", "interactive"], "default": "push"},
        ],
        "presets": [{"label": "解析", "args": ["{agent}", "--mode", "{mode}"]}],
    },
    {
        "id": "smoke-hermes-profiles",
        "name": "Hermes Profile 探针",
        "description": "对所有 hermes_profile agent 做最小 CLI 启动探针（较慢）。",
        "category": "Agent 配置",
        "readonly": True,
        "timeout": 300,
        "presets": [{"label": "探针", "args": []}],
    },
    {
        "id": "inbox-pending-dump",
        "name": "Inbox 待处理摘要",
        "description": "列出指定 agent inbox 中 pending/processing 消息。",
        "category": "Inbox",
        "readonly": True,
        "timeout": 30,
        "params": [
            {"name": "agent", "label": "Agent", "type": "select",
             "options": _AGENT_OPTIONS, "default": _AGENT_OPTIONS[0] if _AGENT_OPTIONS else ""},
        ],
        "presets": [{"label": "查看", "args": ["--agent", "{agent}"]}],
    },
    {
        "id": "fix-cline-auth",
        "name": "修复 Cline 鉴权",
        "description": "同步 Hermes API key、重建 codex 容器、cline auth。需在 WSL 宿主机执行（非容器内）。",
        "category": "Agent 鉴权",
        "readonly": False,
        "host_only": True,
        "timeout": 600,
        "presets": [
            {"label": "全套 (--all)", "args": ["--all"]},
            {"label": "仅同步 .env", "args": ["--sync-env"]},
            {"label": "Smoke 测试", "args": ["--smoke-only"]},
        ],
    },
    {
        "id": "mailbus-doctor-report",
        "name": "Mailbus 全量诊断",
        "description": "路径、Docker（含 WSL）、manifest、framework、API、恢复完整性。等同 mailbus doctor。",
        "category": "迁移与修复",
        "readonly": True,
        "timeout": 90,
        "presets": [{"label": "运行诊断", "args": []}],
    },
    {
        "id": "platform-probe",
        "name": "平台 Agent 实例探测",
        "description": "按当前启动平台（win32/wsl/linux/docker）校验各 Agent 框架实例是否就绪。",
        "category": "Agent 配置",
        "readonly": True,
        "timeout": 60,
        "presets": [
            {"label": "探测全部", "args": ["--json"]},
            {"label": "指定 agent", "args": ["--framework", "{agent}", "--json"]},
        ],
        "params": [
            {"name": "agent", "label": "Agent", "type": "select",
             "options": _AGENT_OPTIONS, "default": _AGENT_OPTIONS[0] if _AGENT_OPTIONS else ""},
        ],
    },
    {
        "id": "check-mailbus-integrity",
        "name": "源码/Store 完整性",
        "description": "检查恢复后关键文件、transport 名册、skills/hermes 目录是否偏少。",
        "category": "迁移与修复",
        "readonly": True,
        "timeout": 30,
        "presets": [{"label": "检查", "args": []}],
    },
    {
        "id": "compose-volumes-check",
        "name": "Compose 挂载校验",
        "description": "检查 docker-compose v3 挂载与 override drift（只读）。",
        "category": "Docker / Compose",
        "readonly": True,
        "timeout": 60,
        "presets": [{"label": "校验", "args": []}],
    },
    {
        "id": "compose-sync-repair",
        "name": "同步 Compose Override",
        "description": "从 transport registry 重新生成 docker-compose.override.yml。",
        "category": "Docker / Compose",
        "readonly": False,
        "host_only": True,
        "timeout": 120,
        "presets": [{"label": "mailbus compose sync", "args": []}],
    },
    {
        "id": "probe-hermes-chat",
        "name": "Hermes 对话探针 (DeepSeek)",
        "description": "WSL 容器内 hermes chat 最小探针 + DEEPSEEK_API_KEY / HERMES_DATA / .sync 检查。",
        "category": "Agent 鉴权",
        "readonly": True,
        "host_only": True,
        "timeout": 120,
        "presets": [{"label": "Hermes 探针", "args": []}],
    },
    {
        "id": "ensure-n8n-publish-workflow",
        "name": "n8n 发布 Workflow",
        "description": "确保 mailbus-multi-publish workflow 已导入并激活（WSL Docker）。",
        "category": "迁移与修复",
        "readonly": False,
        "host_only": True,
        "timeout": 300,
        "presets": [{"label": "Ensure", "args": []}],
    },
    {
        "id": "test-agents",
        "name": "Agent 全量测试",
        "description": "从 config.json 读取全部 agent，逐项验证配置、容器、浏览器 URL、身份文件、AgentMemory。",
        "category": "Agent 配置",
        "readonly": True,
        "timeout": 120,
        "params": [
            {"name": "agent", "label": "Agent（留空=全部）", "type": "text",
             "default": ""},
        ],
        "presets": [
            {"label": "测试全部", "args": ["--json"]},
            {"label": "测试指定 agent", "args": ["agent-a", "--json"]},
            {"label": "交互报表", "args": []},
        ],
    },
    {
        "id": "health-overview",
        "name": "全景体检",
        "description": "一屏汇总：每 agent 浏览器/CLI/容器/身份可达性 + ollama/agentmemory/n8n/comfyui/external-tools 健康。",
        "category": "全景体检",
        "readonly": True,
        "timeout": 120,
        "presets": [
            {"label": "体检", "args": ["--json"]},
            {"label": "交互报表", "args": []},
        ],
    },
]

for t in CLINIC_TOOLS:
    t["_script"] = f"tools/{t['id']}.py"

# tools/test-agents.py → 实际文件是 tools/test_agents.py（underscore 命名）
for t in CLINIC_TOOLS:
    if t["id"] == "test-agents":
        t["_script"] = "tools/test_agents.py"


def list_clinic_tools() -> list[dict]:
    """返回可序列化的工具列表（不含内部字段）。"""
    out = []
    for t in CLINIC_TOOLS:
        item = {k: v for k, v in t.items() if not k.startswith("_")}
        item["script"] = t.get("_script", "")
        out.append(item)
    return out


def _get_tool(tool_id: str) -> Optional[dict]:
    for t in CLINIC_TOOLS:
        if t["id"] == tool_id:
            return t
    return None


def _resolve_args(template: list[str], params: dict) -> list[str]:
    resolved = []
    for a in template:
        if isinstance(a, str) and "{" in a:
            try:
                resolved.append(a.format(**params))
            except KeyError:
                resolved.append(a)
        else:
            resolved.append(str(a))
    return resolved


def run_clinic_tool(
    tool_id: str,
    *,
    preset_index: int = 0,
    params: Optional[dict] = None,
    data_dir: str = "",
) -> dict:
    """执行诊所工具，返回 stdout/stderr/rc。"""
    tool = _get_tool(tool_id)
    if not tool:
        return {"ok": False, "error": "unknown_tool", "tool_id": tool_id}

    params = dict(params or {})
    for p in tool.get("params") or []:
        if p["name"] not in params and p.get("default") is not None:
            params[p["name"]] = p["default"]

    presets = tool.get("presets") or [{"label": "run", "args": []}]
    if preset_index < 0 or preset_index >= len(presets):
        preset_index = 0
    preset = presets[preset_index]
    args = _resolve_args(preset.get("args") or [], params)
    env = os.environ.copy()
    env.update(preset.get("env") or {})
    if data_dir:
        env.setdefault("MAILBUS_DATA_DIR", data_dir)
        env.setdefault("DATA_DIR", data_dir)
    env.setdefault("MAILBUS_URL", DEFAULT_API_BASE)

    script_rel = tool.get("_script", f"tools/{tool_id}.py")
    script_path = os.path.join(MAIL_ROOT, script_rel.replace("/", os.sep))
    if not os.path.isfile(script_path):
        return {"ok": False, "error": "script_missing", "script": script_rel}

    # host_only 工具：如果当前在 Docker 容器内运行，则拒绝执行并提示在宿主机操作
    if tool.get("host_only") and os.path.exists("/.dockerenv"):
        return {
            "ok": False,
            "tool_id": tool_id,
            "tool_name": tool.get("name"),
            "readonly": tool.get("readonly", False),
            "host_only": True,
            "error": "host_only_in_docker",
            "message_zh": f"此工具需要在 WSL 宿主机执行，请在终端手动运行: python3 {script_rel}",
            "stdout": "",
            "stderr": f"[host_only] {tool.get('name')} 不能容器内执行，请 ssh 进 WSL 后手动运行。",
        }

    cmd = [sys.executable, script_path, *args]
    timeout = int(tool.get("timeout") or 120)
    started = now_ts()
    try:
        r = subprocess.run(
            cmd,
            cwd=MAIL_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        elapsed = round(now_ts() - started, 2)
        return {
            "ok": r.returncode == 0,
            "tool_id": tool_id,
            "tool_name": tool.get("name"),
            "readonly": tool.get("readonly", False),
            "host_only": tool.get("host_only", False),
            "command": " ".join(cmd),
            "returncode": r.returncode,
            "elapsed_seconds": elapsed,
            "stdout": (r.stdout or "")[-12000:],
            "stderr": (r.stderr or "")[-4000:],
        }
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "tool_id": tool_id,
            "error": "timeout",
            "timeout_seconds": timeout,
            "stdout": (e.stdout or "")[-8000:] if e.stdout else "",
            "stderr": (e.stderr or "")[-2000:] if e.stderr else "",
        }
    except Exception as e:
        return {"ok": False, "tool_id": tool_id, "error": str(e)}
