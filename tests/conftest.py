"""pytest 公共 fixture — MAILBUS_ROOT / 临时 store。"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lib.constants import MAILBUS_ROOT, MAILBUS_DATA_STR  # noqa: E402
from lib.utils import configure_stdio_utf8  # noqa: E402

configure_stdio_utf8()

# 测试进程统一根路径（#18 P5-R05）
os.environ.setdefault("MAILBUS_ROOT", str(MAILBUS_ROOT))
os.environ.setdefault("MAILBUS_DATA", MAILBUS_DATA_STR)


def pytest_configure(config):
    os.environ.setdefault("MAILBUS_ROOT", str(MAILBUS_ROOT))


import pytest  # noqa: E402


@pytest.fixture
def mailbus_root():
    return MAILBUS_ROOT


@pytest.fixture
def tmp_store():
    with tempfile.TemporaryDirectory(prefix="mailbus-test-") as tmp:
        yield tmp

