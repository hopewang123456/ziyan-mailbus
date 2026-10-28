"""PY4-Option A 渐进路由表 + OpenAPI 生成器测试（2026-10-27 第一批）。"""

from __future__ import annotations

from unittest import mock

from lib.api import routes
from lib.api.openapi import build_openapi


class TestRouteSpecMatch:
    def test_exact_hit_and_miss(self):
        spec = routes.RouteSpec("GET", "/api/health", "system", "handle_health")
        assert spec.match("/api/health") == {}
        assert spec.match("/api/health2") is None
        assert spec.match("/api/other") is None

    def test_param_prefix(self):
        spec = routes.RouteSpec("GET", "/api/workflows/{id}", "workflows", "handle_workflow_get")
        assert spec.match("/api/workflows/bugfix_s") == {"id": "bugfix_s"}
        assert spec.match("/api/workflows/") is None  # 空参数不匹配
        assert spec.match("/api/workflows") is None
        assert spec.match("/api/positions") is None

    def test_multi_path_params(self):
        """多路径参数：/api/tasks/{id}/fsm/{action} → 两个参数按序返回。"""
        spec = routes.RouteSpec(
            "POST", "/api/tasks/{id}/fsm/{action}", "tasks", "handle_task_fsm_action")
        assert spec.path_params == ("id", "action")
        assert spec.match("/api/tasks/t_001/fsm/rollback") == {"id": "t_001", "action": "rollback"}
        assert spec.match("/api/tasks/t_001/fsm") is None
        assert spec.match("/api/tasks/t_001/fsm/a/b") is None


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

    def test_multi_param_dispatch_passes_params_in_order(self):
        """双参 dispatch：handler(task_id, action) 顺序正确。"""
        called = []

        class Mods:
            def handle_task_fsm_action(self, handler_self, task_id, action):
                called.append((task_id, action))

        with mock.patch("lib.api.base._get_handlers", return_value={"tasks": Mods()}):
            assert routes.dispatch(object(), "POST", "/api/tasks/t_9/fsm/rollback") is True
        assert called == [("t_9", "rollback")]

    def test_longer_path_wins_over_shorter(self):
        """/api/inbox/ack/{id} 必须先于 /api/inbox/{agent} 命中。"""
        called = []

        class Mods:
            def handle_inbox_ack(self, handler_self, msg_id):
                called.append(("ack", msg_id))

            def handle_inbox(self, handler_self, agent):
                called.append(("inbox", agent))

        with mock.patch("lib.api.base._get_handlers", return_value={"inbox": Mods()}):
            assert routes.dispatch(object(), "POST", "/api/inbox/ack/m_001") is True
        assert called == [("ack", "m_001")]


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

    def test_path_param_declared_when_not_last_segment(self):
        """参数不在末段时也必须声明（/{id}/delete 这类路由）。"""
        doc = build_openapi()
        entry = doc["paths"]["/api/workflows/{id}/delete"]["post"]
        names = [p["name"] for p in entry["parameters"] if p["in"] == "path"]
        assert "id" in names

    def test_multi_path_params_all_declared(self):
        doc = build_openapi()
        entry = doc["paths"]["/api/tasks/{id}/fsm/{action}"]["post"]
        names = [p["name"] for p in entry["parameters"] if p["in"] == "path"]
        assert names == ["id", "action"]

    def test_request_body_and_response_schema_emitted(self):
        """body_meta / response_meta → requestBody + 带 schema 的 responses。"""
        spec = next(s for s in routes.ROUTES if s.path == "/api/tasks/create")
        assert spec.body_meta, "建任务端点应声明 requestBody"
        doc = build_openapi()
        entry = doc["paths"]["/api/tasks/create"]["post"]
        rb = entry["requestBody"]["content"]["application/json"]["schema"]
        assert rb["type"] == "object"
        assert "properties" in rb
        resp = entry["responses"]["200"]["content"]["application/json"]["schema"]
        assert resp["type"] == "object"

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
        assert suffix_spec.match("/api/workflows/x/delete") == {"id": "x"}
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
