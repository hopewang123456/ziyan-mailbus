"""公开协同 SSE 脱敏：未授权流不得泄露员工标识与 task_id 等内部 ID。"""

from __future__ import annotations

import asyncio

from mailbus.adapters.system.concurrency import StreamGate
from mailbus.adapters.transport.collab_bus import InProcessEventBus
from mailbus.api.sse import _scrub_public, collab_event_stream


def test_scrub_public_strips_internal_ids() -> None:
    pair = _scrub_public(
        "pair.started",
        {
            "pair_id": "p1",
            "initiator_id": "emp_a",
            "partner_id": "emp_b",
            "at": "t",
        },
    )
    assert pair == {"pair_id": "p1", "at": "t"}
    assert "initiator_id" not in pair
    assert "partner_id" not in pair

    task = _scrub_public(
        "task.updated",
        {
            "task_id": "t1",
            "seat_id": "s1",
            "title": "x",
            "state": "running",
            "current_node": "",
            "node_state": "",
            "progress_done": 1,
            "progress_total": 2,
            "updated_at": "t",
        },
    )
    assert "task_id" not in task
    assert task["seat_id"] == "s1"

    # 公开大屏气泡需要 body
    msg = _scrub_public(
        "message.created",
        {"message_id": "m1", "pair_id": "p1", "kind": "note", "body": "hi", "created_at": "t"},
    )
    assert msg["body"] == "hi"

    # 未知事件在公开流直接丢弃
    assert _scrub_public("something.secret", {"secret": "x"}) is None


def _run(coro) -> None:
    asyncio.run(coro)


def test_public_stream_generator_omits_internal_ids() -> None:
    async def main() -> None:
        bus = InProcessEventBus(StreamGate(8))
        out: list[str] = []

        async def drain() -> None:
            async for chunk in collab_event_stream(bus, public=True):
                out.append(chunk)

        task = asyncio.create_task(drain())
        await asyncio.sleep(0.05)  # 等订阅建立
        bus.publish(
            "pair.started",
            {
                "pair_id": "p1",
                "initiator_id": "emp_X",
                "partner_id": "emp_Y",
                "at": "now",
            },
        )
        bus.publish(
            "task.updated",
            {
                "task_id": "task_Z",
                "seat_id": "s1",
                "title": "t",
                "state": "draft",
                "current_node": "",
                "node_state": "",
                "progress_done": 0,
                "progress_total": 0,
                "updated_at": "now",
            },
        )
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        blob = "".join(out)
        assert "emp_X" not in blob
        assert "emp_Y" not in blob
        assert "initiator_id" not in blob
        assert "partner_id" not in blob
        assert "task_Z" not in blob
        assert "task_id" not in blob
        # 脱敏展示数据仍保留
        assert "p1" in blob

    _run(main())


def test_management_stream_keeps_internal_ids() -> None:
    """管理端（public=False）保持完整负载，供控制台展示。"""

    async def main() -> None:
        bus = InProcessEventBus(StreamGate(8))
        out: list[str] = []

        async def drain() -> None:
            async for chunk in collab_event_stream(bus):  # public 默认 False
                out.append(chunk)

        task = asyncio.create_task(drain())
        await asyncio.sleep(0.05)
        bus.publish(
            "pair.started",
            {"pair_id": "p1", "initiator_id": "emp_X", "partner_id": "emp_Y", "at": "now"},
        )
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        blob = "".join(out)
        assert "emp_X" in blob
        assert "initiator_id" in blob

    _run(main())
