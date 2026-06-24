"""pytest 公共 fixture — 确保 PROJECT_ROOT 在 sys.path。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lib.utils import configure_stdio_utf8

configure_stdio_utf8()
