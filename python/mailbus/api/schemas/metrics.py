"""指标与告警规则的对外模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricPointOut(BaseModel):
    metric: str
    value: int | float
    unit: str = "count"
    error: str | None = None


class MetricSeriesOut(BaseModel):
    metric: str
    granularity: str
    points: list[dict[str, Any]] = []


class MetricQueryOut(BaseModel):
    points: list[MetricPointOut]
    series: list[MetricSeriesOut] = []


class MetricRuleOut(BaseModel):
    id: str
    metric: str
    op: str
    threshold: float
    severity: str
    enabled: bool
    note: str
    actions: list[str] = []


class MetricRuleListOut(BaseModel):
    rules: list[MetricRuleOut]


class MetricRuleUpdateIn(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)


class MetricLayoutOut(BaseModel):
    hidden: list[str]


class MetricLayoutViewOut(BaseModel):
    layout: MetricLayoutOut


class MetricLayoutIn(BaseModel):
    hidden: list[str] = Field(default_factory=list)


class MetricManifestOut(BaseModel):
    manifest: dict[str, Any]
