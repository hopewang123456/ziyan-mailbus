#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.pusher import resolve_cli
from lib.utils import json_read
c = json_read("store/config.json")
print(resolve_cli(c["agents"]["lingzhao"], c["agent_types"]))
