#!/usr/bin/env python3
"""关闭 success pipeline 任务在各 agent inbox 的残留消息。"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.commands import load_config
from lib.pipeline_trigger import _close_pipeline_inbox
from lib.utils import resolve_paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id")
    ap.add_argument("--data-dir", default="/mailbus/store")
    args = ap.parse_args()
    cfg = load_config(os.path.join(args.data_dir, "config.json"))
    n = _close_pipeline_inbox(args.data_dir, resolve_paths(args.data_dir), args.task_id, cfg["agents"])
    print(f"closed {n}")


if __name__ == "__main__":
    main()
