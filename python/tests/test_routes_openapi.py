"""PY4-Option A 渐进路由表 + OpenAPI 生成器测试（2026-10-27 第一批）。"""

from __future__ import annotations

from unittest import mock

from lib.api import routes
from lib.api.openapi import build_openapi


class TestRouteSpecMatch:
    def test_exact_hit_and_miss(self):
        spec = routes.RouteSpec("GET", "/api/health", "system", "handle_health")
        assert spec.match("/api/health") == ""
        assert spec.match("/api/health2") is None
        assert spec.match("/api/other") is None

    def test_param_prefix(self):
        spec = routes.RouteSpec("GET", "/api/workflows/{id}", "workflows", "handle_workflow_get")
        assert spec.match("/api/workflows/bugfix_s") == "bugfix_s"
        assert spec.match("/api/workflows/") is None  # 空参数不匹配
        assert spec.match("/api/workflows") is None
        assert spec.match("/api/positions") is None


class TestDispatch:
    def _fake_handler_set(self):
        called = []

        class H:
            def handle_workflow_get(self, handler_self, wf_id):
                called.append(("get", wf_id))

        class Mod:
            handle_workflow_get = H().handle_workflow_get

        return {"workflows": Mod()}, called

    def test_table_hit_invokes_handler_with_param(self):
        h, called = self._fake_handler_set()
        with mock.patch("lib.api.base._get_handlers", return_value=h):
            self_obj = object()
            assert routes.dispatch(self_obj, "GET", "/api/workflows/bugfix_s") is True
        assert called == [("get", "bugfix_s")]

    def test_table_miss_returns_false(self):
        with mock.patch("lib.api.base._get_handlers", return_value={}):
            assert routes.dispatch(object(), "GET", "/api/definitely/not/in/table") is False

    def test_method_must_match(self):
        # GET 路径用 POST 打不中（回退原链）
        with mock.patch("lib.api.base._get_handlers", return_value={}):
            assert routes.dispatch(object(), "POST", "/api/health") is False


class TestOpenApi:
    def test_document_shape(self):
        doc = build_openapi()
        assert doc["openapi"] == "3.1.0"
        assert doc["info"]["title"] == "mailbus-python API"
        assert isinstance(doc["paths"], dict) and len(doc["paths"]) >= 10
        assert "/api/tasks/create" in doc["paths"]
        assert "post" in doc["paths"]["/api/tasks/create"]

    def test_path_param_becomes_parameter(self):
        doc = build_openapi()
        entry = doc["paths"]["/api/workflows/{id}"]["get"]
        assert entry["parameters"][0]["name"] == "id"
        assert entry["parameters"][0]["in"] == "path"

    def test_query_params_from_meta(self):
        doc = build_openapi()
        entry = doc["paths"]["/api/metrics/query"]["get"]
        names = [p["name"] for p in entry["parameters"]]
        assert "metric" in names and "granularity" in names and "hours" in names

    def test_delete_suffix_route_merges_under_own_path(self):
        doc = build_openapi()
        # /api/workflows/{id} 与 /{id}/delete 是两个 path 段（与 python 实际分发一致）
        assert "post" in doc["paths"]["/api/workflows/{id}"]
        assert "post" in doc["paths"]["/api/workflows/{id}/delete"]

    def test_openapi_self_excluded(self):
        doc = build_openapi()
        assert "/api/openapi.json" not in doc["paths"]

    def test_every_route_has_summary_and_tags(self):
        for spec in routes.ROUTES:
            if spec.module == "_openapi":
                continue
            assert spec.summary, f"{spec.method} {spec.path} 缺 summary"
            assert spec.tags, f"{spec.method} {spec.path} 缺 tags"


class TestDispatchPriority:
    def test_suffix_route_captures_param_without_suffix(self):
        """{id}/delete 的 regex 捕获 id（不含后缀）。"""
        suffix_spec = next(s for s in routes.ROUTES if s.path == "/api/workflows/{id}/delete")
        assert suffix_spec.match("/api/workflows/x/delete") == "x"
        assert suffix_spec.match("/api/workflows/x") is None

    def test_delete_routes_to_delete_handler_not_save(self):
        called = []

        class Mods:
            def handle_workflow_delete(self, handler_self, wf_id):
                called.append(("delete", wf_id))

            def handle_workflow_save(self, handler_self, wf_id):
                called.append(("save", wf_id))

        mods = Mods()
        with mock.patch("lib.api.base._get_handlers", return_value={"workflows": mods}):
            assert routes.dispatch(object(), "POST", "/api/workflows/py4_tpl/delete") is True
        assert called == [("delete", "py4_tpl")]
