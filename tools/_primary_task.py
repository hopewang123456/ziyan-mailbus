#!/usr/bin/env python3
"""Round1 工具共用：从 iteration-state 读取主任务 ID。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.iteration_engine import load_primary_task_id

__all__ = ["load_primary_task_id", "primary_task"]

def primary_task(data_dir: str | None = None) -> str:
    data_dir = data_dir or os.environ.get("MAILBUS_DATA", "store")
    return load_primary_task_id(os.path.abspath(data_dir))
