#!/usr/bin/env python3
"""
mailbus-review-watcher.py — 代码审查文件监视器（零侵入自动发现版）
自动扫描指定目录下的所有 git 仓库，发现变更时触发 AI 审查。
无需手动配置，新 clone 的仓库也会自动发现。

启动:
  nohup python3 mailbus-review-watcher.py > /tmp/mailbus-review-watcher.log 2>&1 &
停止:
  kill $(cat /tmp/mailbus-review-watcher.pid)

用法:
  python3 mailbus-review-watcher.py
  python3 mailbus-review-watcher.py --scan-roots /mnt/e /mnt/c/Project
"""

import os, sys, json, time, signal, subprocess, argparse
from datetime import datetime

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "store")
DEFAULT_INTERVAL = 30
RESCAN_INTERVAL = 1800
PID_FILE = "/tmp/mailbus-review-watcher.pid"
STATE_FILE = ".review-watcher-state.json"
DEFAULT_SCAN_ROOTS = ["/mnt/e"]


def _now_tag():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    print(f"[{_now_tag()}] {msg}", flush=True)


def get_head_mtime(repo_path: str) -> float:
    try:
        return os.stat(os.path.join(repo_path, ".git", "HEAD")).st_mtime
    except (FileNotFoundError, PermissionError):
        return 0


def load_state(data_dir: str) -> dict:
    f = os.path.join(data_dir, STATE_FILE)
    if os.path.isfile(f):
        try:
            with open(f) as fp:
                return json.load(fp)
        except Exception:
            return {}
    return {}


def save_state(data_dir: str, state: dict):
    with open(os.path.join(data_dir, STATE_FILE), "w") as fp:
        json.dump(state, fp, indent=2)


def discover_git_repos(scan_roots: list) -> list:
    """扫描根目录（深度有限），返回 [(name, path)]"""
    found = []
    seen = set()

    def _add(name, path):
        p = os.path.normpath(path)
        if p in seen:
            return
        seen.add(p)
        for n2, p2 in found:
            if n2 == name:
                name = f"{os.path.basename(os.path.dirname(p))}-{name}"
                break
        found.append((name, p))

    for root in scan_roots:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            continue
        log(f"  🔍 {root}")
        if os.path.isdir(os.path.join(root, ".git")):
            _add(os.path.basename(root), root)
            continue
        try:
            for entry in sorted(os.listdir(root)):
                sub = os.path.join(root, entry)
                if not os.path.isdir(sub):
                    continue
                if entry.startswith(".") or entry in ("node_modules", "venv", "__pycache__"):
                    continue
                if os.path.isdir(os.path.join(sub, ".git")):
                    _add(entry, sub)
                else:
                    try:
                        for entry2 in sorted(os.listdir(sub)):
                            sub2 = os.path.join(sub, entry2)
                            if os.path.isdir(os.path.join(sub2, ".git")):
                                _add(f"{entry}-{entry2}", sub2)
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError) as e:
            log(f"  ⚠ 跳过 {root}: {e}")
    found.sort(key=lambda x: x[1])
    log(f"  📦 发现 {len(found)} 个 git 仓库")
    for n, p in found:
        log(f"     - {n} ({p})")
    return found

    for root in scan_roots:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            continue
        log(f"  🔍 扫描: {root}")
        try:
            for dirpath, dirnames, _ in os.walk(root, topdown=True, followlinks=False):
                dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
                if ".git" in dirnames:
                    p = os.path.normpath(dirpath)
                    if p in seen:
                        continue
                    seen.add(p)
                    name = os.path.basename(p)
                    # 重名消歧
                    for n2, p2 in found:
                        if n2 == name:
                            name = f"{os.path.basename(os.path.dirname(p))}-{name}"
                            break
                    found.append((name, p))
                    dirnames[:] = []
        except (PermissionError, OSError) as e:
            log(f"  ⚠ 跳过 {root}: {e}")

    found = list(set(found))
    found.sort(key=lambda x: x[1])
    log(f"  📦 发现 {len(found)} 个 git 仓库")
    return found


def trigger_review(repo_name: str, repo_path: str, data_dir: str):
    script = os.path.join(os.path.dirname(__file__), "mailbus-review-cron.py")
    if not os.path.isfile(script):
        log(f"  ⚠ mailbus-review-cron.py 未找到")
        return False
    try:
        r = subprocess.run(
            [sys.executable, script, "--trigger", repo_name,
             "--debounce-minutes", "5", "--data-dir", data_dir],
            capture_output=True, text=True, timeout=180, cwd=repo_path,
        )
        for line in r.stdout.strip().split("\n"):
            line = line.strip()
            if line and "防抖" not in line:
                log(f"  {line}")
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        log(f"  ✗ 审查超时")
        return False


def main():
    parser = argparse.ArgumentParser(description="代码审查监视器（自动发现 git 仓库）")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"检查间隔秒（默认 {DEFAULT_INTERVAL}）")
    parser.add_argument("--scan-roots", nargs="*", default=DEFAULT_SCAN_ROOTS,
                        help=f"扫描根目录（默认 {' '.join(DEFAULT_SCAN_ROOTS)}）")
    parser.add_argument("--rescan-minutes", type=int, default=30,
                        help="重新扫描发现新仓库间隔分钟（默认 30）")
    args = parser.parse_args()

    interval = max(10, args.interval)
    rescan_sec = max(60, args.rescan_minutes * 60)
    data_dir = args.data_dir
    scan_roots = list(args.scan_roots)

    # 把 config.json 中 review_targets 的父目录也加入扫描根
    config_file = os.path.join(data_dir, "config.json")
    if os.path.isfile(config_file):
        with open(config_file) as fp:
            config = json.load(fp)
        for t in config.get("review_targets", []):
            p = t.get("path", "")
            if p and os.path.isdir(p):
                parent = os.path.dirname(os.path.abspath(p))
                if parent not in scan_roots:
                    scan_roots.append(parent)

    # PID 文件
    with open(PID_FILE, "w") as fp:
        fp.write(str(os.getpid()))

    running = True
    def handle_stop(sig, frame):
        nonlocal running
        log("⏹ 收到停止信号，退出")
        running = False
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    log(f"🚀 mailbus 审查监视器 v2（自动发现版）")
    log(f"   间隔={interval}s  重扫描={args.rescan_minutes}分钟")
    log(f"   扫描根: {scan_roots}")
    log(f"   PID={os.getpid()}")

    # 首次发现
    repos = discover_git_repos(scan_roots)
    repo_map = {n: p for n, p in repos}

    state = load_state(data_dir)
    for name, path in repo_map.items():
        if name not in state:
            state[name] = get_head_mtime(path)

    log(f"   追踪中仓库: {len(repo_map)} 个")
    for name, path in sorted(repo_map.items()):
        log(f"     - {name} ({path})")

    last_rescan = time.time()

    while running:
        now = time.time()

        # 定期重新扫描
        if now - last_rescan > rescan_sec:
            log(f"🔄 定期重扫描...")
            new_repos = discover_git_repos(scan_roots)
            added = 0
            for name, path in new_repos:
                if path not in repo_map.values():
                    repo_map[name] = path
                    state[name] = get_head_mtime(path)
                    added += 1
            if added:
                log(f"   ✨ 发现 {added} 个新仓库")
                save_state(data_dir, state)
            last_rescan = now

        # 检查变更
        for name in list(repo_map.keys()):
            if not running:
                break
            path = repo_map.get(name)
            if not path or not os.path.isdir(os.path.join(path, ".git")):
                continue
            cur = get_head_mtime(path)
            last = state.get(name, 0)
            if cur > last:
                log(f"📝 {name}: 检测到代码变更")
                trigger_review(name, path, data_dir)
                state[name] = cur
                save_state(data_dir, state)

        time.sleep(interval)

    if os.path.isfile(PID_FILE):
        os.remove(PID_FILE)
    log("👋 审查监视器已退出")


if __name__ == "__main__":
    main()
