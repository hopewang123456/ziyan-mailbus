"""指标路由：清单/查询/概览/趋势/排行/CSV + 大盘布局。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import metrics as mapper
from mailbus.api.schemas.contract.metric import (
    MetricBreakdownOut,
    MetricManifestOut,
    MetricOverviewOut,
    MetricQueryOut,
    MetricRuleOut,
    MetricRulePageOut,
    MetricTrendOut,
)
from mailbus.api.schemas.metrics import (
    MetricLayoutIn,
    MetricLayoutViewOut,
    MetricRuleUpdateIn,
)
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/metrics", tags=["metric"])


def _service(request: Request):
    return request.app.state.container.metrics


def _csv(content: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([content]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/manifest", response_model=MetricManifestOut, summary="指标口径清单")
def manifest(request: Request) -> MetricManifestOut:
    get_actor(request)
    return MetricManifestOut(manifest=_service(request).manifest())


@router.get("/query", response_model=MetricQueryOut, summary="指标查询")
def query(
    request: Request,
    metric: list[str] | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    granularity: str = "1h",
    hours: int = Query(default=24, ge=1, le=24 * 30),
) -> MetricQueryOut:
    get_actor(request)
    view = _service(request).query(tuple(metric or ()), granularity, hours)
    return mapper.to_query(view)


@router.get("/overview", response_model=MetricOverviewOut, summary="指标概览卡片")
def overview(
    request: Request,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
) -> MetricOverviewOut:
    actor = get_actor(request)
    return MetricOverviewOut(**_service(request).overview_report(actor, from_, to))


@router.get("/trend", response_model=MetricTrendOut, summary="指标趋势")
def trend(
    request: Request,
    metric: list[str] | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    bucket: str = "1h",
) -> MetricTrendOut:
    actor = get_actor(request)
    view = _service(request).trend_report(actor, tuple(metric or ()), from_, to, bucket)
    return MetricTrendOut(**view)


@router.get("/breakdown", response_model=MetricBreakdownOut, summary="指标对比排行")
def breakdown(
    request: Request,
    metric: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
) -> MetricBreakdownOut:
    actor = get_actor(request)
    return MetricBreakdownOut(**_service(request).breakdown_report(actor, metric, from_, to))


@router.get("/export", summary="导出指标 CSV", response_class=StreamingResponse)
def export(
    request: Request,
    metric: list[str] | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
) -> StreamingResponse:
    actor = get_actor(request)
    return _csv(_service(request).export_csv(actor, from_, to), "metrics.csv")


@router.get("/rules", response_model=MetricRulePageOut, summary="告警规则列表")
def list_rules(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> MetricRulePageOut:
    get_actor(request)
    views = _service(request).list_rules()
    return MetricRulePageOut(
        items=[mapper.to_rule(view) for view in views[offset:offset + limit]],
        total=len(views), limit=limit, offset=offset,
    )


@router.get("/rules/{rule_id}", response_model=MetricRuleOut, summary="告警规则详情")
def get_rule(rule_id: str, request: Request) -> MetricRuleOut:
    get_actor(request)
    return mapper.to_rule(_service(request).get_rule(rule_id))


@router.patch(
    "/rules/{rule_id}", response_model=MetricRuleOut, summary="更新告警规则"
)
@declares(Capability.SYSTEM_CONFIG)
def update_rule(
    rule_id: str, payload: MetricRuleUpdateIn, request: Request
) -> MetricRuleOut:
    view = _service(request).update_rule(get_actor(request), rule_id, payload.fields)
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
