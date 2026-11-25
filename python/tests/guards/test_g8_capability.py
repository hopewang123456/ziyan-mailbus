"""G8 权限声明守卫：每个写路由都必须声明所需 capability。

公开入口（public）与仅需登录（self）属于显式例外，必须列在白名单里，
新增时需要人工复核。
"""

from __future__ import annotations

from mailbus.api.deps import PUBLIC, SELF
from mailbus.core.shared.values import Capability

PUBLIC_WRITE_ROUTES = {
    "/api/identity/bootstrap/super-admin",
    "/api/invites/accept",
    "/api/agents/register",
    "/api/public/collab/screens",
    "/api/public/collab/screens/{screen_id}/heartbeat",
    "/api/public/collab/screens/{screen_id}/leave",
}
AGENT_TOKEN_WRITE_ROUTES = {
    "/api/a2a/messages",
}
SELF_WRITE_ROUTES = {
    "/api/identity/staff/{employee_id}/heartbeat",
    "/api/identity/logout",
    "/api/collab/screens/{screen_id}/heartbeat",
    "/api/collab/pairs",
    "/api/collab/pairs/{pair_id}/end",
    "/api/tasks/{task_id}/cancel",
    "/api/tasks/{task_id}/nodes/{node_id}/claim",
    "/api/tasks/{task_id}/nodes/{node_id}/rerun-join",
    "/api/workflows/{workflow_id}/versions/{version}/validate",
}


def _iter_api_routes(routes, prefix: str = ""):
    """递归展开 FastAPI 的 include_router 包装，产出 (path, endpoint, methods)。

    FastAPI 0.163 起 include_router 不再把子路由平铺进 app.routes，而是包成
    ``_IncludedRouter``；直接遍历 app.routes 会漏掉全部子路由（守卫空转）。
    """
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            context = getattr(route, "include_context", None)
            extra = getattr(context, "prefix", "") or ""
            yield from _iter_api_routes(original.routes, prefix + extra)
            continue
        methods = getattr(route, "methods", None)
        if methods:
            yield prefix + route.path, route.endpoint, methods


def test_every_write_route_declares_capability() -> None:
    from mailbus.bootstrap.main import create_app

    valid = {c.value for c in Capability}
    routes = list(_iter_api_routes(create_app().routes))
    assert len(routes) >= 80, f"路由扫描失败：仅发现 {len(routes)} 条路由"
    problems: list[str] = []
    for path, endpoint, methods in routes:
        if not methods & {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        declared = getattr(endpoint, "__mailbus_capability__", None)
        if declared in valid:
            continue
        if declared == PUBLIC and path in PUBLIC_WRITE_ROUTES | AGENT_TOKEN_WRITE_ROUTES:
            continue
        if declared == SELF and path in SELF_WRITE_ROUTES:
            continue
        problems.append(
            f"{sorted(methods)} {path} 未声明有效 capability：{declared!r}"
        )
    assert not problems, "写路由缺少权限声明：\n" + "\n".join(problems)
