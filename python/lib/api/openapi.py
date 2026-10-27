"""OpenAPI 3.1 生成器（PY4-Option A）— 唯一输入是 routes.ROUTES 声明表。

与 java springdoc 同规格（/v3/api-docs），供双栈 API 面对拍（D13 四件套）。
形状声明从轻：paths + summary + tags + path/query 参数；请求/响应体 schema
随路由表化渐进补齐（POST 渐进批）。
"""

from __future__ import annotations

from typing import Any, Dict

from lib.api import routes


def build_openapi() -> Dict[str, Any]:
    paths: Dict[str, Dict[str, Any]] = {}
    for spec in routes.ROUTES:
        if spec.module == "_openapi":
            continue  # 文档自身不进文档
        entry: Dict[str, Any] = {
            "summary": spec.summary,
            "tags": list(spec.tags),
            "operationId": f"{spec.action}",
            "responses": {"200": {"description": "OK"}},
        }
        # 路径参数
        if spec.path.endswith("}"):
            pname = spec.path[spec.path.index("{") + 1 : -1]
            entry["parameters"] = [{
                "name": pname,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }]
        for pname, pin, pdesc in spec.params_meta:
            entry.setdefault("parameters", []).append({
                "name": pname,
                "in": pin,
                "required": pin == "path",
                "description": pdesc,
                "schema": {"type": "string"},
            })
        method = spec.method.lower()
        # /api/workflows/{id} 与 /api/workflows/{id}/delete 共享 path 段：合并
        for existing_path, node in paths.items():
            if existing_path == spec.path:
                node[method] = entry
                break
        else:
            paths[spec.path] = {method: entry}

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "mailbus-python API",
            "version": "1.0.0",
            "description": "声明式路由表生成（PY4-A）；java 对等面见 /v3/api-docs（springdoc）",
        },
        "paths": paths,
        "tags": sorted({t for spec in routes.ROUTES for t in spec.tags}),
    }


def handle_openapi(handler) -> None:
    handler._send_json(build_openapi())
