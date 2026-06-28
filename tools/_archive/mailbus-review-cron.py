#!/usr/bin/env python3
"""
ziyan-mailbus 自动代码审查（事件驱动版）
支持两种模式：

  1. 轮询模式（cron）:  全量扫描 review_targets
     python3 mailbus-review-cron.py [--data-dir PATH]

  2. 触发模式（git hook）:  指定单仓审查，带防抖
     python3 mailbus-review-cron.py --trigger <name> [--debounce-minutes 10]

安装 git hook:
  python3 mailbus-review-cron.py --install-hooks
"""

import os
import sys
import json
import subprocess
import argparse
import time
from datetime import datetime, timezone, timedelta

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "store")
STATE_FILE = ".review-state.json"
DEBOUNCE_DEFAULT = 10  # 默认防抖 10 分钟


def _now_cn():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+0800")


def _now_ts() -> float:
    return time.time()


def load_config(data_dir: str) -> dict:
    config_file = os.path.join(data_dir, "config.json")
    if not os.path.isfile(config_file):
        print(f"✗ config.json 未找到: {config_file}")
        sys.exit(1)
    with open(config_file) as f:
        return json.load(f)


def _load_state(data_dir: str) -> dict:
    state_file = os.path.join(data_dir, STATE_FILE)
    if os.path.isfile(state_file):
        try:
            with open(state_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_state(data_dir: str, state: dict):
    state_file = os.path.join(data_dir, STATE_FILE)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def get_last_reviewed(data_dir: str, repo_name: str) -> str:
    state = _load_state(data_dir)
    entry = state.get(repo_name, {})
    if isinstance(entry, str):
        return entry  # 旧格式兼容
    return entry.get("commit", "")


def get_last_review_time(data_dir: str, repo_name: str) -> float:
    state = _load_state(data_dir)
    entry = state.get(repo_name, {})
    if isinstance(entry, str):
        return 0
    return entry.get("timestamp", 0)


def save_last_reviewed(data_dir: str, repo_name: str, commit_hash: str):
    state = _load_state(data_dir)
    state[repo_name] = {
        "commit": commit_hash,
        "timestamp": _now_ts(),
        "reviewed_at": _now_cn(),
    }
    _save_state(data_dir, state)


def get_head_commit(repo_path: str) -> str:
    """获取仓库当前 HEAD commit hash"""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=15,
            cwd=repo_path,
        )
        if r.returncode == 0:
            return r.stdout.strip()
        return ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def run_review(repo_path: str, repo_name: str, config: dict | None = None):
    """调用 review.py 审查"""
    candidates = []
    if config and config.get("review_script"):
        candidates.append(os.path.normpath(config["review_script"]))
    if os.environ.get("MAILBUS_REVIEW_SCRIPT"):
        candidates.append(os.path.normpath(os.environ["MAILBUS_REVIEW_SCRIPT"]))
    mail_home = os.environ.get("MAIL_HOME", os.path.dirname(os.path.abspath(__file__)))
    candidates += [
        os.path.join(mail_home, "..", "pr-agent", "review.py"),
        os.path.expanduser("~/pr-agent/review.py"),
    ]
    review_script = None
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.isfile(c):
            review_script = c
            break

    if not review_script:
        print(f"  ✗ review.py 未找到")
        return False

    cmd = [sys.executable, review_script, "--output", "/dev/stdout", "--repo-name", repo_name]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=180,
            cwd=repo_path,
        )
        if r.returncode == 0:
            for line in r.stdout.split("\n"):
                if "报告已存档:" in line:
                    report_path = line.split("报告已存档:")[-1].strip()
                    print(f"  ✓ 审查完成: {report_path}")
                    return True
            if "没有代码变更" in r.stdout:
                print(f"  - 无代码变更")
                return True
            print(f"  ✓ 审查完成（报告已自动存档）")
            return True
        else:
            print(f"  ✗ 审查失败: {r.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ✗ 审查超时（180s）")
        return False


def _notify_xiaoqi(data_dir: str, repo_name: str):
    """审查完成后通知小七"""
    msg_id = f"review-{int(time.time())}"
    msg = {
        "id": msg_id,
        "from": "mailbus",
        "to": "xiaoqi",
        "type": "notice",
        "priority": "normal",
        "content": f"🔍 {repo_name} 有新代码审查报告，请查看 dashboard 🔍 tab",
        "status": "pending",
        "created_at": _now_cn(),
    }
    inbox_file = f"{data_dir}/inbox/xiaoqi/inbox.json"
    if not os.path.exists(os.path.dirname(inbox_file)):
        return
    import json
    inbox_data = json_read(inbox_file, {"agent": "xiaoqi", "has_unread": False, "messages": [], "since": _now_cn()})
    inbox_data.setdefault("messages", []).append(msg)
    inbox_data["has_unread"] = True
    json_write(inbox_file, inbox_data)


def scan_one(data_dir: str, target: dict, debounce_minutes: int = 0, config: dict | None = None) -> bool:
    """扫描单个仓库，返回是否有变更并执行了审查"""
    name = target.get("name", "?")
    path = target.get("path", "")

    if not path or not os.path.isdir(path):
        print(f"  ⚠ {name}: 目录不存在 ({path})，跳过")
        return False
    if not os.path.isdir(os.path.join(path, ".git")):
        print(f"  ⚠ {name}: 不是 git 仓库 ({path})，跳过")
        return False

    # 防抖检查（仅 trigger 模式使用）
    if debounce_minutes > 0:
        last_time = get_last_review_time(data_dir, name)
        elapsed = (_now_ts() - last_time) / 60
        if elapsed < debounce_minutes:
            print(f"  - {name}: 防抖中（上次 {elapsed:.0f} 分钟前，防抖 {debounce_minutes} 分钟）")
            return False

    head = get_head_commit(path)
    if not head:
        print(f"  ⚠ {name}: 无法获取 HEAD，跳过")
        return False

    last = get_last_reviewed(data_dir, name)
    if last == head:
        print(f"  ✓ {name}: 无新变更 (HEAD 未变)")
        return False

    print(f"  🔍 {name}: 检测到新 commit ({head[:12]})")
    ok = run_review(path, name, config=config)
    if ok:
        save_last_reviewed(data_dir, name, head)
        # 通知小七有新审查报告
        try:
            _notify_xiaoqi(data_dir, name)
        except Exception:
            pass
    print()
    return ok


# ── git hook 安装 ──

HOOK_SCRIPT = """#!/bin/bash
# 自动代码审查 hook — 由 mailbus-review-cron.py 安装
# commit/merge 后触发审查，带防抖
set -euo pipefail

REVIEW_CRON="/mnt/e/ai_tools/mail/mailbus-review-cron.py"
REPO_NAME="{repo_name}"

if [ ! -f "$REVIEW_CRON" ]; then
    exit 0
fi

python3 "$REVIEW_CRON" --trigger "$REPO_NAME" --debounce-minutes {debounce} > /dev/null 2>&1 &
exit 0
"""


def install_hooks(data_dir: str, debounce_minutes: int = DEBOUNCE_DEFAULT):
    """为所有 review_targets 仓库安装 post-commit + post-merge hook"""
    config = load_config(data_dir)
    targets = config.get("review_targets", [])

    if not targets:
        print("ℹ 未配置 review_targets，跳过")
        return

    installed = 0
    failed = 0

    for target in targets:
        name = target.get("name", "?")
        path = target.get("path", "")
        git_dir = os.path.join(path, ".git")

        if not os.path.isdir(git_dir):
            print(f"  ⚠ {name}: 不是 git 仓库 ({path})，跳过")
            failed += 1
            continue

        hooks_dir = os.path.join(git_dir, "hooks")
        os.makedirs(hooks_dir, exist_ok=True)

        for hook_name in ("post-commit", "post-merge"):
            hook_path = os.path.join(hooks_dir, hook_name)
            script = HOOK_SCRIPT.format(repo_name=name, debounce=debounce_minutes)

            with open(hook_path, "w") as f:
                f.write(script)
            os.chmod(hook_path, 0o755)
            print(f"  ✓ {name}: .git/hooks/{hook_name} 已安装")

        installed += 1

    print()
    if installed > 0:
        print(f"✅ 成功安装 {installed} 个仓库的 git hook（防抖 {debounce_minutes} 分钟）")
    if failed > 0:
        print(f"⚠  {failed} 个仓库跳过（目录不存在或非 git 仓库）")


# ── 主入口 ──


def main():
    parser = argparse.ArgumentParser(
        description="ziyan-mailbus 自动代码审查 — 事件驱动版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 mailbus-review-cron.py                        # 全量扫描（cron 模式）
  python3 mailbus-review-cron.py --trigger mailbus       # 单仓触发
  python3 mailbus-review-cron.py --install-hooks         # 安装 git hook
        """,
    )
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument("--trigger", metavar="NAME", help="单仓触发审查")
    parser.add_argument("--debounce-minutes", type=int, default=DEBOUNCE_DEFAULT,
                        help=f"防抖分钟数（默认 {DEBOUNCE_DEFAULT}，仅 trigger 模式生效）")
    parser.add_argument("--install-hooks", action="store_true", help="安装 git hook 到目标仓库")
    args = parser.parse_args()

    # ── 安装 hook ──
    if args.install_hooks:
        install_hooks(args.data_dir, args.debounce_minutes)
        return

    config = load_config(args.data_dir)
    targets = config.get("review_targets", [])

    if not targets:
        print("ℹ 未配置 review_targets，跳过")
        return

    # ── 触发模式 ──
    if args.trigger:
        name = args.trigger
        target = next((t for t in targets if t.get("name") == name), None)
        if not target:
            print(f"✗ 未找到仓库: {name}")
            print(f"  可用: {[t.get('name') for t in targets]}")
            sys.exit(1)
        print(f"⚡ 触发审查 — {name} ({_now_cn()})")
        scan_one(args.data_dir, target, debounce_minutes=args.debounce_minutes, config=config)
        return

    # ── 轮询模式 ──
    print(f"📋 自动代码审查 — {_now_cn()}")
    print(f"   待扫描仓库: {len(targets)} 个")
    print()

    changed = 0
    for target in targets:
        if scan_one(args.data_dir, target, config=config):
            changed += 1

    print(f"✅ 本轮审查完成，{changed} 个仓库有变更")


if __name__ == "__main__":
    main()
