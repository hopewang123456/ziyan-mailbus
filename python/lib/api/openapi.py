"""OpenAPI 3.1 生成器（PY4-Option A）— 唯一输入是 routes.ROUTES 声明表。

与 java springdoc 同规格（/v3/api-docs），供双栈 API 面对拍（D13 四件套）。
形状声明：paths + summary + tags + path/query 参数 + requestBody/responses
schema（由 RouteSpec.body_meta / response_meta 声明）。
"""

from __future__ import annotations

from typing import Any, Dict

from lib.api import routes

_JSON_TYPES = {"string", "integer", "number", "boolean", "array", "object"}


def _schema_for(ptype: str) -> Dict[str, Any]:
    """声明类型 → OpenAPI schema；未知类型回落 string。"""
    return {"type": ptype if ptype in _JSON_TYPES else "string"}


def _object_schema(fields: tuple) -> Dict[str, Any]:
    """((name, type, desc), ...) → object schema（properties + required）。"""
    properties: Dict[str, Any] = {}
    required = []
    for f in fields:
        name, ftype, fdesc = (list(f) + ["string", ""])[:3]
        properties[name] = _schema_for(ftype)
        if fdesc:
            properties[name]["description"] = fdesc
        required.append(name)
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


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
        # 路径参数：路径中每个 {param} 都要声明（参数不在末段时同样需要，
        # 否则 /{id}/delete 这类路由的 path 参数在文档里丢失——2026-10-27 修）
        for pname in spec.path_params:
            entry.setdefault("parameters", []).append({
                "name": pname,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            })
        for pmeta in spec.params_meta:
            pname, pin, pdesc = pmeta[0], pmeta[1], pmeta[2]
            ptype = pmeta[3] if len(pmeta) > 3 else "string"
            entry.setdefault("parameters", []).append({
                "name": pname,
                "in": pin,
                "required": pin == "path",
                "description": pdesc,
                "schema": _schema_for(ptype),
            })
        # 请求体
        if spec.body_meta:
            entry["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {"schema": _object_schema(spec.body_meta)},
                },
            }
        # 响应体
        if spec.response_meta:
            entry["responses"] = {
                "200": {
                    "description": "OK",
                    "content": {
                        "application/json": {"schema": _object_schema(spec.response_meta)},
                    },
                },
            }
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
