"""协同视图映射：大屏与结对。"""

from __future__ import annotations

from mailbus.api.schemas.collab import PairOut
from mailbus.api.schemas.contract.screen import ScreenConfigIn, ScreenConfigOut, ScreenOut
from mailbus.application.collab.pairs import PairView
from mailbus.application.collab.screens import ScreenConfigView, ScreenView


def to_pair(view: PairView) -> PairOut:
    return PairOut(
        pair_id=view.pair_id,
        initiator_id=view.initiator_id,
        partner_id=view.partner_id,
        state=view.state,
        created_at=view.created_at,
        ended_at=view.ended_at,
    )


def to_screen_view(view: ScreenView) -> ScreenOut:
    return ScreenOut(
        screen_id=view.screen_id,
        name=view.name,
        source=view.source,
        online=view.online,
        last_seen_at=view.last_seen_at,
        config_version=view.config_version,
        published_config_version=view.published_config_version,
        team_bound=view.team_bound,
        play_state=view.play_state,
    )


def to_screen_config(view: ScreenConfigView) -> ScreenConfigOut:
    config = ScreenConfigIn(**view.config) if view.config else None
    return ScreenConfigOut(
        screen_id=view.screen_id,
        config_version=view.config_version,
        published_config_version=view.published_config_version,
        updated_at=view.updated_at,
        play_state=view.play_state,
        config=config,
    )
