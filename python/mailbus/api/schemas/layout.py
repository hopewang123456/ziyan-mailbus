"""孪生布局的对外模型，字段与 web/src/twin/types.ts 一一对应。"""

from __future__ import annotations

from pydantic import BaseModel


class SeatAgentOut(BaseModel):
    agent_id: str
    display_name: str
    position: str
    team: str
    status: str
    task: str
    last_heartbeat: str
    bound_agent_id: str = ""
    agent_name: str = ""
    agent_framework: str = ""
    task_id: str = ""
    task_state: str = ""
    current_node: str = ""
    node_state: str = ""
    progress_done: int = 0
    progress_total: int = 0
    pair_id: str = ""
    partner_name: str = ""


class LayoutSeatOut(BaseModel):
    seat_id: str
    x: float
    y: float
    rotation: float
    agent: SeatAgentOut | None = None


class LayoutRoomOut(BaseModel):
    room_id: str
    name: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    seats: list[LayoutSeatOut]


class LayoutFloorOut(BaseModel):
    floor_id: str
    name: str
    level: int
    rooms: list[LayoutRoomOut]


class OfficeSiteOut(BaseModel):
    site_id: str
    name: str
    org_name: str
    floors: list[LayoutFloorOut]


class PublicSeatAgentOut(BaseModel):
    """公开大屏的脱敏投影：不含 agent 台账 id、端点与心跳。"""

    display_name: str
    position: str
    team: str
    status: str
    task: str
    agent_name: str = ""
    agent_framework: str = ""
    task_state: str = ""
    current_node: str = ""
    node_state: str = ""
    progress_done: int = 0
    progress_total: int = 0
    pair_id: str = ""
    partner_name: str = ""


class PublicLayoutSeatOut(BaseModel):
    seat_id: str
    x: float
    y: float
    rotation: float
    agent: PublicSeatAgentOut | None = None


class PublicLayoutRoomOut(BaseModel):
    room_id: str
    name: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    seats: list[PublicLayoutSeatOut]


class PublicLayoutFloorOut(BaseModel):
    floor_id: str
    name: str
    level: int
    rooms: list[PublicLayoutRoomOut]


class PublicOfficeSiteOut(BaseModel):
    site_id: str
    name: str
    org_name: str
    floors: list[PublicLayoutFloorOut]
