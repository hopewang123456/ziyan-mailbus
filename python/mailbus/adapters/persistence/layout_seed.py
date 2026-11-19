"""只读空间种子的 JSON 适配器。

种子是静态几何（site/floor/room/seat），不参与事务；读取一次后缓存。
"""

from __future__ import annotations

import json
from pathlib import Path

from mailbus.core.org.errors import LayoutSeedError
from mailbus.core.org.models import FloorDef, LayoutDef, RoomDef, SeatDef
from mailbus.core.org.values import RoomKind


class JsonLayoutSeed:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._cached: LayoutDef | None = None

    def load(self) -> LayoutDef:
        if self._cached is None:
            self._cached = self._read()
        return self._cached

    def _read(self) -> LayoutDef:
        if not self._path.exists():
            raise LayoutSeedError(f"布局种子不存在：{self._path}")
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LayoutSeedError(f"布局种子无法解析：{exc}") from exc
        try:
            return _parse(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise LayoutSeedError(f"布局种子结构非法：{exc}") from exc


def _parse(raw: dict) -> LayoutDef:
    floors = tuple(_floor(item) for item in raw["floors"])
    layout = LayoutDef(
        site_id=raw["site_id"],
        name=raw["name"],
        org_name=raw["org_name"],
        floors=floors,
    )
    seats = layout.seats()
    if len({seat.seat_id for seat in seats}) != len(seats):
        raise LayoutSeedError("布局种子存在重复 seat_id")
    return layout


def _floor(raw: dict) -> FloorDef:
    return FloorDef(
        floor_id=raw["floor_id"],
        name=raw["name"],
        level=int(raw["level"]),
        rooms=tuple(_room(item) for item in raw["rooms"]),
    )


def _room(raw: dict) -> RoomDef:
    return RoomDef(
        room_id=raw["room_id"],
        name=raw["name"],
        kind=RoomKind(raw["kind"]),
        x=float(raw["x"]),
        y=float(raw["y"]),
        w=float(raw["w"]),
        h=float(raw["h"]),
        seats=tuple(_seat(item) for item in raw.get("seats", [])),
    )


def _seat(raw: dict) -> SeatDef:
    return SeatDef(
        seat_id=raw["seat_id"],
        x=float(raw["x"]),
        y=float(raw["y"]),
        rotation=float(raw.get("rotation", 0)),
    )
