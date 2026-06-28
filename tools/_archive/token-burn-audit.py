#!/usr/bin/env python3
"""一次性诊断：mailbus token 消耗可疑点。"""
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
STORE = os.path.join(ROOT, "store")


def main():
    cron = os.path.join(STORE, "cron.log")
    if os.path.isfile(cron):
        text = open(cron, encoding="utf-8", errors="replace").read()
        print("=== cron.log 统计 ===")
        print(f"scan 总次数: {len(re.findall(r'scheduler job=scan start', text))}")
        for agent in ("lingjian", "lingxiao", "lingxun", "lingzhao", "lingyan"):
            n = len(re.findall(rf"{agent} \(", text))
            print(f"  推送日志含 {agent}: {n}")
        print(f"僵尸回收行数: {len(re.findall(r'回收 \\d+ 条僵尸', text))}")
        print(f"orch_reset_inbox=24: {len(re.findall('orch_reset_inbox=24', text))}")
        for day in ("2026-06-15", "2026-06-17", "2026-06-18"):
            c = len(re.findall(day + r".*scheduler job=scan start", text))
            if c:
                print(f"  scan {day}: {c} 次")

    cfg = json.load(open(os.path.join(STORE, "config.json"), encoding="utf-8"))
    print("\n=== config 催办/重试 ===")
    print(f"reminder_minutes: {cfg.get('reminder_minutes')}")
    print(f"max_reminders: {cfg.get('max_reminders')}")
    print(f"max_retries (push): {cfg.get('max_retries', 3)}")

    agents = list(cfg.get("agents", {}).keys())
    print("\n=== inbox 活跃/高重推消息 ===")
    hot = []
    for a in agents:
        p = os.path.join(STORE, "inbox", a, "inbox.json")
        if not os.path.isfile(p):
            continue
        data = json.load(open(p, encoding="utf-8"))
        for m in data.get("messages", []):
            st = m.get("state") or m.get("status", "")
            pc = m.get("pushed_count") or 0
            rc = m.get("reminded_count") or 0
            if st in ("processing", "pushed", "resending", "pending") or pc > 1 or rc > 1:
                hot.append((a, m.get("id", ""), st, pc, rc, m.get("type"), (m.get("content") or "")[:80]))
    hot.sort(key=lambda x: (-x[3], -x[4]))
    for row in hot[:25]:
        print(f"  {row[0]}: id={row[1][:36]} state={row[2]} pushed={row[3]} reminded={row[4]} type={row[5]}")
        print(f"    {row[6]}")

    al = os.path.join(STORE, "audit_log")
    if os.path.isdir(al):
        files = os.listdir(al)
        print(f"\n=== audit_log: {len(files)} 文件 ===")
        by_task = Counter()
        for f in files:
            key = f.rsplit("-r", 1)[0] if "-r" in f else f
            by_task[key] += 1
        for k, v in by_task.most_common(8):
            print(f"  {k}: {v}")

    tasks_dir = os.path.join(STORE, "tasks")
    running = []
    if os.path.isdir(tasks_dir):
        for f in os.listdir(tasks_dir):
            if not f.endswith(".json"):
                continue
            t = json.load(open(os.path.join(tasks_dir, f), encoding="utf-8"))
            if t.get("status") == "running":
                running.append(t)
    print(f"\n=== running tasks: {len(running)} ===")
    by_person = Counter()
    for t in running:
        chain = t.get("chain") or []
        person = chain[-1].get("to_person") if chain else t.get("assignee", "?")
        by_person[person] += 1
        print(f"  {t.get('task_id')} -> {person} reminded={t.get('reminded_count', 0)}")
    print("  按 assignee:", dict(by_person))

    # Hermes session dumps today (proxy for LLM calls)
    hermes = "/mnt/e/hermes-data/.hermes/profiles"
    if os.path.isdir(r"E:\hermes-data\.hermes\profiles"):
        hermes = r"E:\hermes-data\.hermes\profiles"
    dumps = 0
    for root, _, files in os.walk(hermes):
        for f in files:
            if f.startswith("request_dump_") and ("20260617" in f or "20260618" in f or "20260615" in f):
                dumps += 1
    print(f"\n=== Hermes request_dump (6/15-18): {dumps} ===")
    by_profile = Counter()
    for root, _, files in os.walk(hermes):
        for f in files:
            if f.startswith("request_dump_") and "20260617" in f:
                prof = root.replace("\\", "/").split("/profiles/")[-1].split("/")[0]
                by_profile[prof] += 1
    for k, v in by_profile.most_common(12):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
