"""指标域契约模型：清单、查询、概览/趋势/排行、规则与导出。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mailbus.api.schemas.contract.common import Page
from mailbus.api.schemas.metrics import (
    MetricManifestOut,
    MetricPointOut,
    MetricQueryOut,
    MetricRuleOut,
    MetricSeriesOut,
)

__all__ = [
    "MetricManifestOut",
    "MetricPointOut",
    "MetricQueryOut",
    "MetricRuleOut",
    "MetricRulePageOut",
    "MetricSeriesOut",
    "MetricOverviewOut",
    "MetricTrendOut",
    "MetricBreakdownOut",
    "MetricBreakdownItemOut",
]


class MetricRulePageOut(Page[MetricRuleOut]):
    pass


class MetricOverviewOut(BaseModel):
    start: str
    end: str
    cards: list[MetricPointOut] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=dict)


class MetricTrendOut(BaseModel):
    start: str
    end: str
    bucket: str
    series: list[MetricSeriesOut] = Field(default_factory=list)


class MetricBreakdownItemOut(BaseModel):
    key: str
    label: str
    value: int | float


class MetricBreakdownOut(BaseModel):
    start: str
    end: str
    metric: str | None = None
    items: list[MetricBreakdownItemOut] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
