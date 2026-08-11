"""Wave7: container path helpers baseline."""
from __future__ import annotations

import os

import pytest

from lib.infra.utils import CONTAINER_STORE_MARKERS, to_container_store_path


def test_markers_include_phase3_paths():
    for marker in (
        "work-orders/",
        "deliverables/",
        "human-queue",
        "agentmemory-pending/",
    ):
        assert marker in CONTAINER_STORE_MARKERS


def test_to_container_store_path_windows():
    data = r"E:\ai_tools\mail\store"
    p = os.path.join(data, "msg-files", "msg-1.md")
    assert to_container_store_path(data, p) == "/mailbus/store/msg-files/msg-1.md"


def test_to_container_work_orders():
    data = r"E:\ai_tools\mail\store"
    p = os.path.join(data, "work-orders", "task-1", "step-2.md")
    assert to_container_store_path(data, p) == "/mailbus/store/work-orders/task-1/step-2.md"


def test_to_container_deliverables():
    data = r"E:\ai_tools\mail\store"
    p = os.path.join(data, "deliverables", "game-1", "README.md")
    assert to_container_store_path(data, p) == "/mailbus/store/deliverables/game-1/README.md"
