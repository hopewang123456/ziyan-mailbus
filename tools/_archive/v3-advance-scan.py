#!/usr/bin/env python3
"""V3 推进：housekeeping(pipeline_trigger) + scan 推送。"""
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.commands import load_config, _run_scan_once_body
from lib.scanner import run_housekeeping

cfg = load_config(os.path.join(MAIL, "store", "config.json"))
data_dir = cfg["data_dir"]
agents = cfg.get("agents", {})
print("--- housekeeping (pipeline_trigger) ---")
run_housekeeping(data_dir, agents)
print("--- scan ---")
_run_scan_once_body(data_dir, cfg, quiet=False)
