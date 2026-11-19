"""指标路由：口径清单、查询、告警规则与大盘布局。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import metrics as mapper
from mailbus.api.schemas.metrics import (
    MetricLayoutIn,
    MetricLayoutViewOut,
    MetricManifestOut,
    MetricQueryOut,
    MetricRuleListOut,
    MetricRuleOut,
    MetricRuleUpdateIn,
)
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/metrics", tags=["metric"])


def _service(request: Request):
    return request.app.state.container.metrics


@router.get("/manifest", response_model=MetricManifestOut, summary="指标口径清单")
def manifest(request: Request) -> MetricManifestOut:
    get_actor(request)
    return MetricManifestOut(manifest=_service(request).manifest())


@router.get("/query", response_model=MetricQueryOut, summary="指标查询")
def query(
    request: Request,
    metric: list[str] | None = Query(default=None),
    granularity: str = "1h",
    hours: int = Query(default=24, ge=1, le=24 * 30),
) -> MetricQueryOut:
    get_actor(request)
    view = _service(request).query(tuple(metric or ()), granularity, hours)
    return mapper.to_query(view)


@router.get("/rules", response_model=MetricRuleListOut, summary="告警规则")
def list_rules(request: Request) -> MetricRuleListOut:
    get_actor(request)
    return MetricRuleListOut(
        rules=[mapper.to_rule(item) for item in _service(request).list_rules()]
    )


@router.patch(
    "/rules/{rule_id}", response_model=MetricRuleOut, summary="更新告警规则"
)
@declares(Capability.SYSTEM_CONFIG)
def update_rule(
    rule_id: str, payload: MetricRuleUpdateIn, request: Request
) -> MetricRuleOut:
    view = _service(request).update_rule(
        get_actor(request), rule_id, payload.fields
    )
    return mapper.to_rule(view)


@router.get("/layout", response_model=MetricLayoutViewOut, summary="大盘布局")
def layout(request: Request) -> MetricLayoutViewOut:
    get_actor(request)
    return mapper.to_layout(_service(request).layout())


@router.patch("/layout", response_model=MetricLayoutViewOut, summary="更新大盘布局")
@declares(Capability.SYSTEM_CONFIG)
def update_layout(payload: MetricLayoutIn, request: Request) -> MetricLayoutViewOut:
    view = _service(request).update_layout(get_actor(request), payload.hidden)
    return mapper.to_layout(view)
