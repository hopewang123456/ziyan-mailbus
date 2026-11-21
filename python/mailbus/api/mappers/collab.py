"""协同视图映射：大屏与结对。"""

from __future__ import annotations

from mailbus.api.schemas.collab import PairOut, ScreenOut
from mailbus.application.collab.pairs import PairView
from mailbus.application.collab.screens import ScreenView


def to_pair(view: PairView) -> PairOut:
    return PairOut(
        pair_id=view.pair_id,
        initiator_id=view.initiator_id,
        partner_id=view.partner_id,
        state=view.state,
        created_at=view.created_at,
        ended_at=view.ended_at,
    )


def to_screen(view: ScreenView) -> ScreenOut:
    return ScreenOut(
        screen_id=view.screen_id,
        name=view.name,
        floor_id=view.floor_id,
        seat_id=view.seat_id,
        online=view.online,
        last_seen=view.last_seen,
        secret=view.secret,
    )
