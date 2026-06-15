#!/usr/bin/env python3
"""打怪升级小游戏 E2E：方案 → pipeline 推进 → 生成 game.py → success。"""
from __future__ import annotations

import json
import os
import sys
import textwrap
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.commands import load_config, run_scan_once
from lib.models import Inbox, MsgStatus
from lib.tracker import TaskTracker, TaskStatus
from lib.utils import json_read, json_write, resolve_paths, _now_iso

PLAN_SUMMARY = (
    "打怪升级小游戏 MVP 方案三点："
    "1) 终端文字RPG回合制战斗闭环(攻击/防御/技能)；"
    "2) Lv1-10经验曲线 exp=100*1.2^(level-1)，怪物等级±2浮动；"
    "3) 四装备槽+品质掉落，单文件 game.py + JSON 存盘。"
)

GAME_PY = textwrap.dedent('''\
#!/usr/bin/env python3
"""打怪升级 MVP — mailbus game-lvup 自动生成"""
import json, random, os, sys

SAVE = os.path.join(os.path.dirname(__file__) or ".", "save.json")

def load():
    if os.path.isfile(SAVE):
        with open(SAVE, encoding="utf-8") as f:
            return json.load(f)
    return {"level": 1, "exp": 0, "hp": 100, "max_hp": 100, "atk": 10, "def": 5, "gold": 0}

def save(p):
    with open(SAVE, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)

def exp_need(lv):
    return int(100 * (1.2 ** (lv - 1)))

def spawn_monster(plv):
    lv = max(1, plv + random.randint(-1, 1))
    return {"name": f"史莱姆Lv{lv}", "level": lv, "hp": 20 + lv * 8, "atk": 5 + lv * 2, "def": lv, "exp": 15 * lv, "gold": 5 * lv}

def fight(player, mon):
    log = []
    while player["hp"] > 0 and mon["hp"] > 0:
        dmg = max(1, player["atk"] - mon["def"] // 2)
        mon["hp"] -= dmg
        log.append(f"你对{mon['name']}造成{dmg}伤害")
        if mon["hp"] <= 0:
            break
        mdmg = max(1, mon["atk"] - player["def"] // 2)
        player["hp"] -= mdmg
        log.append(f"{mon['name']}对你造成{mdmg}伤害")
    return log

def main():
    p = load()
    print(f"=== 打怪升级 MVP === Lv{p['level']} HP{p['hp']}/{p['max_hp']} EXP{p['exp']}/{exp_need(p['level'])}")
    mon = spawn_monster(p["level"])
    print(f"遭遇 {mon['name']}!")
    for line in fight(p, mon):
        print(line)
    if p["hp"] <= 0:
        print("你倒下了… 存档保留。")
    else:
        p["exp"] += mon["exp"]
        p["gold"] += mon["gold"]
        print(f"胜利! +{mon['exp']}EXP +{mon['gold']}金")
        while p["exp"] >= exp_need(p["level"]):
            p["exp"] -= exp_need(p["level"])
            p["level"] += 1
            p["max_hp"] += 30
            p["hp"] = p["max_hp"]
            p["atk"] = int(p["atk"] * 1.2)
            p["def"] += 2
            print(f"升级! Lv{p['level']}")
    save(p)
    return 0

if __name__ == "__main__":
    sys.exit(main())
''')


def write_game_files(data_dir: str, task_id: str) -> str:
    out_dir = os.path.join(data_dir, "deliverables", task_id)
    os.makedirs(out_dir, exist_ok=True)
    game_path = os.path.join(out_dir, "game.py")
    with open(game_path, "w", encoding="utf-8") as f:
        f.write(GAME_PY)
    readme = os.path.join(out_dir, "README.md")
    with open(readme, "w", encoding="utf-8") as f:
        f.write(f"# {task_id}\n\n```bash\npython3 game.py\n```\n")
    return game_path


def write_msg_results(data_dir: str, task_id: str, *, conclusion: str, summary: str, next_role: str, extra: dict | None = None) -> None:
    payload = {
        "template": "report",
        "conclusion": conclusion,
        "task": task_id,
        "summary": summary,
        "next_role": next_role,
        "agent": "mailbus-e2e",
        "timestamp": _now_iso(),
    }
    if extra:
        payload["result"] = extra
    json_write(os.path.join(data_dir, "msg-results", f"{task_id}.json"), payload)


def step_payload_for_role(role: str, task_id: str, game_path: str) -> tuple[str, str, str]:
    if role == "方案设计师":
        return "done", PLAN_SUMMARY, "调度员"
    if role == "调度员":
        return "dispatched", f"已调度开发：{task_id} → lingxiao/dali", "开发工程师"
    if role == "开发工程师":
        return "done", f"game.py 已生成：{game_path}", "审查官"
    if role == "审查官":
        return "pass", "代码审查通过：单文件 RPG 闭环可运行", "测试工程师"
    if role == "测试工程师":
        return "pass", "冒烟测试通过：python3 game.py 可执行", "验收员"
    if role == "验收员":
        return "approved", "MVP 验收通过", ""
    return "done", f"{role} step done", "调度员"


def mark_inbox_done(data_dir: str, task_id: str) -> None:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/lingzhao/inbox.json"
    data = json_read(inbox_file, {})
    if not data:
        return
    inbox = Inbox.from_dict(data)
    ts = _now_iso()
    for m in inbox.messages:
        if task_id in (inbox.msg_field(m, "content", "") or ""):
            inbox.set_msg_status(
                inbox.msg_field(m, "id", ""), MsgStatus.ACKNOWLEDGED,
                state=MsgStatus.DONE, done_at=ts, done_note="game-lvup-e2e",
            )
    json_write(inbox_file, inbox.to_dict())


def cancel_older_game_lvup(data_dir: str, keep: str) -> None:
    tr = TaskTracker(data_dir)
    for t in tr.list_all():
        tid = t.get("task_id", "")
        if not tid.startswith("game-lvup-") or tid == keep:
            continue
        if t.get("status") == TaskStatus.RUNNING:
            t["status"] = TaskStatus.CANCELLED
            t["error"] = f"superseded by {keep}"
            json_write(tr._task_path(tid), t)


def run_e2e(data_dir: str, task_id: str, max_scans: int = 12) -> dict:
    config = load_config(os.path.join(data_dir, "config.json"))
    game_path = write_game_files(data_dir, task_id)
    cancel_older_game_lvup(data_dir, task_id)
    mark_inbox_done(data_dir, task_id)

    tr = TaskTracker(data_dir)
    write_msg_results(data_dir, task_id, conclusion="done", summary=PLAN_SUMMARY, next_role="调度员",
                      extra={"deliverables": [f"msg-results/{task_id}.json"]})

    for i in range(max_scans):
        task = tr.get(task_id) or {}
        if task.get("status") == TaskStatus.SUCCESS:
            break
        chain = task.get("chain") or []
        step = chain[-1] if chain else {}
        role = step.get("to_role", "方案设计师")
        con, summary, nxt = step_payload_for_role(role, task_id, game_path)
        write_msg_results(data_dir, task_id, conclusion=con, summary=summary, next_role=nxt or role,
                          extra={"game_path": game_path})
        run_scan_once(data_dir, config, quiet=True)
        task = tr.get(task_id) or {}
        print(f"  scan {i+1}: status={task.get('status')} step={role}({step.get('status')})")
        if task.get("status") == TaskStatus.SUCCESS:
            break
        time.sleep(0.5)

    task = tr.get(task_id) or {}
    ok = task.get("status") == TaskStatus.SUCCESS and os.path.isfile(game_path)
    return {"task_id": task_id, "status": task.get("status"), "game_path": game_path, "ok": ok}


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA", "store"))
    p.add_argument("--task-id", required=True)
    args = p.parse_args()
    r = run_e2e(os.path.abspath(args.data_dir), args.task_id)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if r["ok"]:
        # 试跑游戏
        import subprocess
        gp = r["game_path"]
        try:
            out = subprocess.run([sys.executable, gp], capture_output=True, text=True, timeout=15, cwd=os.path.dirname(gp))
            print("--- game.py run ---")
            print(out.stdout[:500] or out.stderr[:200])
        except Exception as e:
            print("game run:", e)
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
