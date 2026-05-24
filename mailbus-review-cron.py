#!/usr/bin/env python3
"""
ziyan-mailbus 自动代码审查（cron 轮询版）
按 config.json 中的 review_targets 列表扫描各仓库的新 commit，
发现变更后自动调用 review.py 审查并存档。

用法:
  python3 mailbus-review-cron.py [--data-dir PATH]
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime, timezone, timedelta

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "store")


def _now_cn():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+0800")


def load_config(data_dir: str) -> dict:
    config_file = os.path.join(data_dir, "config.json")
    if not os.path.isfile(config_file):
        print(f"✗ config.json 未找到: {config_file}")
        sys.exit(1)
    with open(config_file) as f:
        return json.load(f)


def get_last_reviewed(data_dir: str, repo_name: str) -> str:
    """读取上次审查时的 commit hash"""
    state_file = os.path.join(data_dir, ".review-state.json")
    if os.path.isfile(state_file):
        try:
            with open(state_file) as f:
                state = json.load(f)
            return state.get(repo_name, "")
        except (json.JSONDecodeError, IOError):
            return ""
    return ""


def save_last_reviewed(data_dir: str, repo_name: str, commit_hash: str):
    """记录本次审查的 commit hash"""
    state_file = os.path.join(data_dir, ".review-state.json")
    state = {}
    if os.path.isfile(state_file):
        try:
            with open(state_file) as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            state = {}
    state[repo_name] = commit_hash
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


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


def run_review(repo_path: str, repo_name: str):
    """调用 review.py 审查"""
    review_script = os.path.join(os.path.dirname(__file__), "..", "pr-agent", "review.py")
    review_script = os.path.normpath(review_script)
    if not os.path.isfile(review_script):
        # 也试试绝对路径
        review_script = "/mnt/e/ai_tools/pr-agent/review.py"
        if not os.path.isfile(review_script):
            print(f"  ✗ review.py 未找到")
            return False

    cmd = [sys.executable, review_script, "--output", "/dev/stdout"]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=180,
            cwd=repo_path,
        )
        # review.py 内部已自动存档到 store/reports/
        if r.returncode == 0:
            # 提取存档路径（review.py 会打印 "报告已存档: ..."）
            for line in r.stdout.split("\n"):
                if "报告已存档:" in line:
                    report_path = line.split("报告已存档:")[-1].strip()
                    print(f"  ✓ 审查完成: {report_path}")
                    return True
            # 没有变更也算成功
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


def main():
    parser = argparse.ArgumentParser(description="ziyan-mailbus 自动代码审查")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="mailbus 数据目录")
    args = parser.parse_args()

    config = load_config(args.data_dir)
    targets = config.get("review_targets", [])

    if not targets:
        print("ℹ 未配置 review_targets，跳过")
        return

    print(f"📋 自动代码审查 — {_now_cn()}")
    print(f"   待扫描仓库: {len(targets)} 个")
    print()

    for target in targets:
        name = target.get("name", "?")
        path = target.get("path", "")
        if not path or not os.path.isdir(path):
            print(f"  ⚠ {name}: 目录不存在 ({path})，跳过")
            continue
        if not os.path.isdir(os.path.join(path, ".git")):
            print(f"  ⚠ {name}: 不是 git 仓库 ({path})，跳过")
            continue

        head = get_head_commit(path)
        if not head:
            print(f"  ⚠ {name}: 无法获取 HEAD，跳过")
            continue

        last = get_last_reviewed(args.data_dir, name)
        if last == head:
            print(f"  ✓ {name}: 无新变更 (HEAD 未变)")
            continue

        print(f"  🔍 {name}: 检测到新 commit ({head[:12]})")
        ok = run_review(path, name)
        if ok:
            save_last_reviewed(args.data_dir, name, head)
        print()

    print("✅ 本轮审查完成")


if __name__ == "__main__":
    main()
