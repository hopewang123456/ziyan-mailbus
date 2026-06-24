#!/usr/bin/env python3
"""手动触发一次 lingxun 零 LLM 巡检 notice（测试/运维用）。"""
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.jobs import run_lingxun_patrol

if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(MAIL, "store")
    raise SystemExit(run_lingxun_patrol(data_dir))
