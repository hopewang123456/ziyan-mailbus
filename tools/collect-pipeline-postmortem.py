#!/usr/bin/env python3
"""Collect pipeline blockers + token burn data for game-courier live acceptance."""
from __future__ import annotations

import json
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.commands import load_config
from lib.models import Inbox
from lib.task_fsm import get_active_step
from lib.tracker import TaskTracker
from lib.utils import json_read, json_write, resolve_paths, _now_iso

TASK_ID = "game-courier-20260625"

# 已知卡点（live 验收中观测 + 修复状态）
KNOWN_BLOCKERS = [
    {
        "id": "win-docker-push",
        "step": None,
        "symptom": "Windows 宿主机 scan 无法直接 docker exec，replies 报「docker 不是内部或外部命令」",
        "root_cause": "pusher 用 shell=True 调 docker，Win 无 docker 在 PATH",
        "fix": "pusher._docker_push_argv() → WSL bash -lc",
        "fallback": "scan 只在 WSL/Docker mailbus 容器内跑，或强制走 WSL 包装",
        "status": "fixed",
    },
    {
        "id": "phantom-cooldown",
        "step": None,
        "symptom": "phantom 重置 pending 后仍 15min cooldown 不重推",
        "root_cause": "reset pending 未清 last_pushed_at",
        "fix": "scanner pending 重置清 last_pushed_at；pushed_count=0 跳过 cooldown",
        "fallback": "tools/reset-pipeline-current-step.py + blocking scan",
        "status": "fixed",
    },
    {
        "id": "to_agent-scan",
        "step": None,
        "symptom": "pipeline 消息不进队列 / 无法插队",
        "root_cause": "Envelope v3 用 to_agent，scanner 只认 to_person",
        "fix": "scanner 双字段识别 + recover pipeline_by_agent",
        "fallback": None,
        "status": "fixed",
    },
    {
        "id": "openclaw-timeout-120",
        "step": 4,
        "symptom": "xiaoqi Step4 pushed 后无 step-s4.json，openclaw agent 120s 超时",
        "root_cause": "OpenClawAdapter --timeout 120 短于 pipeline 实际耗时",
        "fix": "openclaw --timeout 对齐 push_timeout_pipeline (600s)",
        "fallback": "reset + 手动 blocking scan",
        "status": "fixed",
    },
    {
        "id": "inbox-closed-no-result",
        "step": 6,
        "symptom": "lingxiao inbox msg=closed 但 step-s6.json 不存在，pipeline 永久卡住",
        "root_cause": "Codex CLI 结束未落盘 msg-results，状态却被标 closed/done",
        "fix": "reset 脚本支持 closed/done/acknowledged；scanner 回复不再无验收标 done；pusher phantom 检测应 reset",
        "fallback": "reset-pipeline-current-step.py + defer-lingjian-audit.py + blocking scan",
        "status": "fixed",
    },
    {
        "id": "corrupt-remind-tasks",
        "step": None,
        "symptom": "scan 崩溃 UnicodeDecodeError / WinError 5 写 task json",
        "root_cause": "store/tasks/remind-*.json 损坏或非 UTF-8",
        "fix": "json_read UnicodeDecodeError 容错；清理 remind-*.json",
        "fallback": "tracker.list_all 跳过坏文件",
        "status": "mitigated",
    },
    {
        "id": "lingyun-powershell-msg",
        "step": 6,
        "symptom": "lingyun push ~4s 失败，replies 报 ParserError TerminatorExpectedAtEndOfString",
        "root_cause": "claude_code Windows 走 powershell -Command 内联 MSG，pipeline 消息含换行/引号破坏 PS 解析",
        "fix": "claude_launch.try_build_push_direct() + pusher 直连 argv；MSG 占位符 PowerShell 单引号转义",
        "fallback": "reset-pipeline-current-step.py + blocking scan",
        "status": "fixed",
    },
    {
        "id": "win-file-lock-permission",
        "step": None,
        "symptom": "watch/scan 崩溃 PermissionError 无法打开 ziyan-mailbus-*.lock",
        "root_cause": "Windows Temp 多进程争用锁文件",
        "fix": "file_lock 打开失败重试；单 bus serve + 单 watch",
        "fallback": "MAILBUS_LOCK_DIR 指向 store/.locks",
        "status": "mitigated",
    },
    {
        "id": "codex-cli-active-false-positive",
        "step": 8,
        "symptom": "lingjian pipeline msg 卡 processing，scan 不重推；容器内另有 audit codex 在跑",
        "root_cause": "CodexAdapter.cli_active_in_ps 任意 codex exec 即 true，无法区分并发任务",
        "fix": "cli_active 按 msg_id 或 _ACTIVE_CLI_PROCS 判断；或单 agent 串行队列",
        "fallback": "reset-pipeline-current-step.py + blocking scan",
        "status": "mitigated",
    },
    {
        "id": "codex-slot-primary-gate",
        "step": 8,
        "symptom": "主 pipeline 在 lingjian 步骤时 side-audit 仍派发/推送，抢占 Codex 单槽",
        "root_cause": "dispatch_pending_audits 每轮 scan 无 primary 互斥；cli_active 任意 codex exec 即 true",
        "fix": "side_audit_deferred_for_reviewer + build_queues 跳过 audit-req；cli_active_in_ps_for(msg_id)",
        "fallback": "tools/defer-lingjian-audit.py 手动归档 audit；reset-pipeline-current-step.py",
        "status": "fixed",
    },
    {
        "id": "bus-serve-down",
        "step": None,
        "symptom": "仅 watch 脚本在跑，scan 全被 mailbus-scan 锁跳过或无人调度",
        "root_cause": "bus serve 进程退出后无内置 scheduler",
        "fix": "确保 bus.py serve 常驻；或 cron blocking scan",
        "fallback": "python -c \"named_lock + _run_scan_once_body\"",
        "status": "ops",
    },
    {
        "id": "deliverable-no-interactive",
        "step": "5-6",
        "symptom": "README 交互模式无法选路线；run_game 忽略 auto 参数",
        "root_cause": "验收仅 pytest + --auto；main 非 auto 仍 run_game(auto=True) 一次跑完",
        "fix": "patch-courier-interactive.py：run_round + input A/B/C",
        "fallback": "人工补测交互；门禁加 scripted stdin",
        "status": "fixed_locally",
        "delivery": "undelivered_at_live",
    },
    {
        "id": "win-ps1-bom",
        "step": "9-12",
        "symptom": ".\\play.ps1 ParserError 缺少右括号",
        "root_cause": "play.ps1 UTF-8 无 BOM，PS 5.1 误解析中文串",
        "fix": "fix-courier-windows-launch.py：UTF-8 BOM + ASCII 提示",
        "fallback": "直接用 python -m game.main --plain",
        "status": "fixed_locally",
        "delivery": "undelivered_at_live",
    },
    {
        "id": "win-bat-wrong-default",
        "step": "9-12",
        "symptom": "play.bat 双击为自动演示非交互",
        "root_cause": "交付 bat 默认 --auto --seed 42",
        "fix": "fix-courier-windows-launch.py：默认交互 + --plain",
        "fallback": "play-auto.bat 单独自动",
        "status": "fixed_locally",
        "delivery": "undelivered_at_live",
    },
    {
        "id": "win-ansi-blank",
        "step": "9-12",
        "symptom": "Win 终端像空白/空行",
        "root_cause": "未默认 --plain；ANSI+Unicode 框线不可读",
        "fix": "patch-courier-main-win.py + plain ASCII 框线",
        "fallback": "--plain 手动加参",
        "status": "fixed_locally",
        "delivery": "undelivered_at_live",
    },
    {
        "id": "win-interactive-flow",
        "step": "6-9",
        "symptom": "交互轮次先无信件、重复 intro",
        "root_cause": "main 在 run_round 前未 prepare_round",
        "fix": "fix-courier-windows-launch.py：prepare_round",
        "fallback": None,
        "status": "fixed_locally",
        "delivery": "undelivered_at_live",
    },
    {
        "id": "acceptance-auto-only",
        "step": "9-12",
        "symptom": "pipeline success 但玩家无法交互玩",
        "root_cause": "s9/s12 只验 pytest + --auto",
        "fix": "见 deliverable-no-interactive 等补丁",
        "fallback": "人工试玩",
        "status": "process_gap",
        "delivery": "undelivered_at_live",
    },
]

# live 验收后人工补丁 = 当时未交付（测试未覆盖）
POST_LIVE_PATCHES = [
    {
        "script": "tools/patch-courier-interactive.py",
        "touches": ["game/engine.py", "game/main.py", "play.ps1"],
        "gap_ids": ["deliverable-no-interactive", "acceptance-auto-only"],
        "should_have_been_caught_by": ["s6 自测", "s9 灵验", "s12 小七"],
    },
    {
        "script": "tools/patch-courier-main-win.py",
        "touches": ["game/main.py", "play.ps1", "play.bat"],
        "gap_ids": ["win-ansi-blank"],
        "should_have_been_caught_by": ["s9 Win 冒烟"],
    },
    {
        "script": "tools/fix-courier-windows-launch.py",
        "touches": [
            "play.ps1",
            "play.bat",
            "play-auto.bat",
            "game/main.py",
            "game/engine.py",
            "game/render.py",
            "play-courier-game.ps1 (repo root)",
        ],
        "gap_ids": [
            "win-ps1-bom",
            "win-bat-wrong-default",
            "win-ansi-blank",
            "win-interactive-flow",
            "win-launch-missing",
        ],
        "should_have_been_caught_by": ["s9 灵验", "s12 小七", "子言试玩"],
    },
]

# Token 消耗热点与省钱建议
TOKEN_BURN_POINTS = [
    {
        "where": "Hermes 方案/调研 (s1-s3)",
        "agents": ["lingzhao", "lingxi"],
        "model": "deepseek-chat (flash)",
        "why_heavy": "多轮读 rules + deliverables + 长方案输出",
        "save": "方案步用 flash 足够；research 可限 max_chars；rules 按需注入 L0 而非全文",
    },
    {
        "where": "OpenClaw 调度 (s4)",
        "agents": ["xiaoqi"],
        "model": "deepseek-chat",
        "why_heavy": "拆单读 scheme+research 全文；失败重推双倍",
        "save": "dispatch 模板化输出；超时一次到位避免重跑",
    },
    {
        "where": "编码步 (s5-s6)",
        "agents": ["dali", "lingyun"],
        "model": "dali=deepseek-flash; lingyun=minimax-m2 (Claude Code)",
        "why_heavy": "整包代码生成 + 多文件读写",
        "save": "s5 dali flash；s6 改派 lingyun 避免 lingxiao codex 重试；pin prefer_agent",
    },
    {
        "where": "编码步 — 推荐",
        "agents": ["lingyun", "dali"],
        "model": "lingyun=minimax-m2 (Claude Code); dali=deepseek-flash",
        "why_heavy": "灵云 pro 档比反复 codex 重试便宜",
        "save": "constraints.dispatch.prefer_agent=lingyun；flash 日常 dali；MAILBUS_ALLOW_PRO=1 仅长 refactor",
    },
    {
        "where": "审查/测试 (s7-s9)",
        "agents": ["lingjin", "lingjian", "lingyan"],
        "model": "hermes/codex/claude 混合",
        "why_heavy": "全量读 src + 跑 pytest",
        "save": "审查只传 diff/变更文件列表；测试用 smoke 子集",
    },
    {
        "where": "scan 自愈 / watch",
        "agents": ["mailbus"],
        "model": "N/A",
        "why_heavy": "多实例 watch + 频繁 scan 重复读 config/inbox",
        "save": "单 serve + 单 watch；scan interval≥30s",
    },
]


def _step_files(data_dir: str) -> list[str]:
    d = os.path.join(data_dir, "msg-results", TASK_ID)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if re.match(r"step-s\d+\.json", f))


def _inbox_retries(data_dir: str, agents: list[str]) -> list[dict]:
    paths = resolve_paths(data_dir)
    rows = []
    for agent in agents:
        inbox = Inbox.from_dict(json_read(os.path.join(paths["inbox"], agent, "inbox.json"), {}))
        for m in inbox.messages:
            content = inbox.msg_field(m, "content", "") or ""
            if TASK_ID not in content:
                continue
            rows.append({
                "agent": agent,
                "msg_id": inbox.msg_field(m, "id", ""),
                "state": inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", ""),
                "pushed_count": inbox.msg_field(m, "pushed_count", 0),
                "last_pushed_at": inbox.msg_field(m, "last_pushed_at", ""),
            })
    return rows


def _tail_jsonl(path: str, n: int = 20) -> list:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        out = []
        for line in lines[-n:]:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        return out
    except OSError:
        return []


def collect(data_dir: str) -> dict:
    cfg = load_config(os.path.join(data_dir, "config.json"))
    agents_cfg = cfg.get("agents", {})
    task = TaskTracker(data_dir).get(TASK_ID) or {}
    active = get_active_step(task) or {}
    steps = _step_files(data_dir)
    step_nums = sorted(int(re.search(r"s(\d+)", f).group(1)) for f in steps if re.search(r"s(\d+)", f))

    dev_agents = ["dali", "lingxiao", "lingyun"]
    retries = _inbox_retries(data_dir, list(agents_cfg.keys()))

    logs_dir = os.path.join(data_dir, "logs")
    scan_skipped = _tail_jsonl(os.path.join(logs_dir, "scan-skipped.jsonl"), 30)
    skip_reasons = {}
    for row in scan_skipped:
        r = row.get("reason", "?")
        skip_reasons[r] = skip_reasons.get(r, 0) + 1

    return {
        "task_id": TASK_ID,
        "collected_at": _now_iso(),
        "pipeline": {
            "status": task.get("status"),
            "active_step": active.get("step"),
            "assignee": active.get("to_agent") or active.get("to_person"),
            "completed_steps": step_nums,
            "max_completed": max(step_nums) if step_nums else 0,
            "target_steps": 12,
        },
        "blockers": {
            "known": KNOWN_BLOCKERS,
            "inbox_retries": retries,
            "scan_skip_counts": skip_reasons,
        },
        "undelivered_at_live": {
            "principle": "凡 post-live 补丁脚本修改过的交付物能力，均视为 pipeline 未交付、测试未覆盖",
            "patches": POST_LIVE_PATCHES,
            "test_gaps": [
                "s9 仅 pytest + --auto，无 scripted stdin 交互",
                "无 Windows .\\play.ps1 / play.bat 双击冒烟",
                "无 scheme 玩法条款 checklist",
                "s12 未在真实 Win 终端试玩",
            ],
        },
        "token_analysis": {
            "burn_points": TOKEN_BURN_POINTS,
            "routing_recommendation": {
                "coding_steps": "优先 lingyun（minimax-m2，单价低）+ dali（flash 快改）；避免 lingxiao codex 与 dali 双轨重复",
                "envelope": "constraints.dispatch.prefer_agent: lingyun 或 pin_agent: dali",
                "tier": "默认 flash；仅 complexity=high 时 model_tier: pro + MAILBUS_ALLOW_PRO=1",
            },
        },
        "fixes_to_apply_next_run": [
            "primary pipeline 运行期间 side-audit 自动 defer（已实现）",
            "Codex 单槽按 msg_id 检测 CLI 占用（已实现）",
            "scanner is_current_pipeline_assignee 参数顺序修复（防 3 次催办误关）",
            "审查步骤 failover 按工种：审查官(5)→开发(8)→方案/架构(1)，非人名硬编码",
            "静默失败 8min 自动工种 failover + 舰队监控告警",
            "bus serve / watch 重启加载新 scanner",
            "验收前 check-preflight 增加 claude_code + codex 槽位检查",
            "交付物门禁：交互 stdin + Win play.ps1/play.bat + scheme 玩法 checklist",
        ],
        "fallback_playbook": {
            "step8_lingjian_stuck": [
                "python tools/defer-lingjian-audit.py",
                "python tools/reset-pipeline-current-step.py",
                "若 Codex 推 3 次仍无 step 结果：python tools/tools/ops/reassign-pipeline-step.py --task-id game-courier-20260625 --failover",
                "或手动：--agent lingyun --from-agent lingjian",
                "blocking scan 一次，等待 10–15min，勿频繁 scan",
            ],
            "reviewer_failover_chain": [
                "同工种 role_type=5 其他候选人",
                "相近工种 priority: developer(8) → planner/架构(1)",
                "配置 pipeline_ops.role_failover.5.similar_role_types",
            ],
            "api_stall_network": [
                "检测 replies 中 connection refused / timeout / fetch failed 等",
                "pipeline_ops.api_stall.repush_wait_minutes 默认 5 分钟后重推",
                "子言面板：舰队监控 → 告警（type=api_unreachable）",
            ],
            "phantom_done_no_step_result": [
                "reset-pipeline-current-step.py（清 done_at/done_note/reminded_count）",
                "确认 scanner 已加载 pipeline verify + 催办保护后再 scan",
            ],
            "lingyun_powershell_parser": [
                "确认 pusher 走 try_build_push_direct（Windows 宿主机）",
                "reset + blocking scan",
            ],
        },
    }


def main() -> int:
    mail = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(mail, "store")
    payload = collect(data_dir)
    out = os.path.join(data_dir, "msg-results", f"{TASK_ID}-postmortem.json")
    json_write(out, payload)
    print(f"written {out}")
    print(f"steps {payload['pipeline']['completed_steps']} / 12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
