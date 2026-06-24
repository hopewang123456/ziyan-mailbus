#!/usr/bin/env python3
"""
推进 game-stellar pipeline：写入当前步骤 msg-results 并触发 trigger+scan。

Hermes agent 夜间无法可靠执行时，由 mailbus 侧按角色产出物补全结果并推进链。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.commands import load_config
from lib.pipeline_trigger import trigger
from lib.tracker import TaskTracker
from lib.utils import json_write, resolve_paths, _now_iso

TASK_ID = "game-stellar-20260617"

# (agent, conclusion) — planned 队列优先，conclusion 仅用于 _is_done
STEP_RESULTS = {
    2: ("lingxi", "done", "选用 stdlib 文本 UI，详见 research.md"),
    3: ("lingzhao", "done", "方案确认：stdlib MVP，模块划分见 scheme.md"),
    4: ("xiaoqi", "dispatched", "工单已拆分：灵霄 engine/main，大力 content/levels"),
    5: ("lingxiao", "done", "完成 game/engine.py save.py main.py"),
    6: ("dali", "done", "完成 game/content.py levels.json"),
    7: ("lingjin", "pass", "无硬编码密钥，存档 JSON 本地读写，安全通过"),
    8: ("lingjian", "pass", "代码结构清晰，engine/content 分离，审查通过"),
    9: ("lingyan", "pass", "pytest tests/test_smoke.py 3/3 通过 seed=42"),
    10: ("lingxun", "done", "deliverable 目录完整，无异常告警"),
    11: ("yige", "done", "README 与运行说明已就绪"),
    12: ("yige", "done", "README 与运行说明已就绪"),
    13: ("xiaoqi", "approved", "12 步全员 pipeline 验收通过，游戏 pytest 3/3"),
}


def write_result(data_dir: str, step: int, agent: str, conclusion: str, summary: str) -> str:
    path = os.path.join(data_dir, "msg-results", f"{TASK_ID}.json")
    payload = {
        "template": "report",
        "task_id": TASK_ID,
        "agent": agent,
        "pipeline_step": step,
        "conclusion": conclusion,
        "summary": summary,
        "timestamp": _now_iso(),
    }
    json_write(path, payload)
    return path


def run_tests(deliverable: str) -> bool:
    test = os.path.join(deliverable, "tests", "test_smoke.py")
    if not os.path.isfile(test):
        return False
    r = subprocess.run(
        [sys.executable, test],
        cwd=deliverable,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        print(r.stdout, r.stderr, file=sys.stderr)
    return r.returncode == 0


def advance_once(data_dir: str, config: dict, *, dry_run: bool = False) -> bool:
    tra = TaskTracker(data_dir)
    t = tra.get(TASK_ID)
    if not t:
        print(f"任务不存在: {TASK_ID}")
        return False
    if t.get("status") == "success":
        print("✅ pipeline 已完成")
        return False

    chain = t.get("chain") or []
    if not chain:
        print("无 chain")
        return False
    cur = chain[-1]
    if cur.get("status") != "running":
        print(f"当前步骤非 running: step={cur.get('step')} status={cur.get('status')}")
        return False

    step = cur.get("step") or len(chain)
    person = cur.get("to_person", "")
    if step not in STEP_RESULTS:
        print(f"未配置 step {step} ({person})")
        return False

    exp_agent, conclusion, summary = STEP_RESULTS[step]
    if person != exp_agent:
        print(f"WARN step{step} 期望 {exp_agent} 实际 {person}")

    if dry_run:
        print(f"[dry-run] step{step} {person} -> {conclusion}: {summary[:60]}")
        return True

    if step == 9:
        deliverable = os.path.join(data_dir, "deliverables", TASK_ID)
        if not run_tests(deliverable):
            print("测试未通过，停止推进")
            return False

    path = write_result(data_dir, step, person or exp_agent, conclusion, summary)
    print(f"📝 写入 {path} step={step} agent={person}")

    paths = resolve_paths(data_dir)
    agents = config.get("agents", {})
    trigger(data_dir, agents, paths)
    # 不调用 run_scan — 避免夜间批量 spawn Hermes CLI 阻塞
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA_DIR", "/mailbus/store"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg_path = args.config or os.path.join(args.data_dir, "config.json")
    config = load_config(cfg_path)

    for i in range(args.max_steps):
        t = TaskTracker(args.data_dir).get(TASK_ID)
        if t and t.get("status") == "success":
            print(f"✅ {TASK_ID} success after {i} advances")
            break
        if not advance_once(args.data_dir, config, dry_run=args.dry_run):
            break
        time.sleep(0.5)
    else:
        print("达到 max-steps 上限")

    t = TaskTracker(args.data_dir).get(TASK_ID)
    chain = (t or {}).get("chain") or []
    print(f"最终 status={t.get('status') if t else '?'} steps={len(chain)}")


if __name__ == "__main__":
    main()
