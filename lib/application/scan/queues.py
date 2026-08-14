"""Queue build / mark pushed (Wave1-D logical module).

Implementation currently lives in lib.application.scan.inbox; this module is the
stable import surface for queue responsibilities.
"""
from __future__ import annotations

from lib.application.scan.inbox import (
    _agent_has_active_work,
    _cleanup_stale_queue_files,
    _get_acked_ids,
    _has_pushed_message,
    build_queues,
    finalize_auto_ack,
    finalize_processing_on_push,
    mark_as_pushed,
    push_to_queue,
    update_message_status,
)

__all__ = [
    "build_queues",
    "finalize_auto_ack",
    "finalize_processing_on_push",
    "mark_as_pushed",
    "push_to_queue",
    "update_message_status",
    "_cleanup_stale_queue_files",
    "_get_acked_ids",
    "_has_pushed_message",
    "_agent_has_active_work",
]
