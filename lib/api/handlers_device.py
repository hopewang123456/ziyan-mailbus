"""mailbus HTTP API — Device Bridge 路由处理器。

处理: POST /api/device/chat（通讯式一轮一答 / 可选 SSE）、POST /api/device/task（工单）、GET /api/device/chat/<ticket_id>（超时取票）。
鉴权独立于 mailbus API token：设备 token（Authorization Bearer / X-Mailbus-Device-Token）。
"""
from __future__ import annotations

import json

from lib.application.device_bridge import (
    DeviceBridgeError,
    deliver_and_wait,
    load_bridge_config,
    resolve_device,
    resolve_ticket,
    set_memory_recorder,
)
from lib.api.handlers_tasks import create_task_from_envelope
from lib import composition  # 跨层解耦：api→adapter 通过 composition 拿服务


def _write_device_memory(data_dir, agent_id, device_id, text, msg_id, role) -> None:
    """实际记忆落盘：SQLite 同步 + AgentMemory 后台线程降级，均不抛异常。"""
    import threading

    # 跨层解耦：api→adapter 通过 composition 拿服务（2026-09 治理）
    mb = composition.memory_bridge_module()

    from_agent = f"device:{device_id}" if role == "user" else agent_id
    key_id = msg_id if role == "user" else f"{msg_id}-assistant"

    if mb.bridge_sqlite_enabled():
        try:
            mb.write_memory_to_sqlite(agent_id, key_id, text, from_agent, "notice")
        except Exception:
            pass

    if mb.bridge_agentmemory_enabled():
        def _am_write():
            try:
                if mb.agentmemory_healthy():
                    mb.write_memory_to_agentmemory(agent_id, key_id, text, from_agent, "notice")
            except Exception:
                pass

        threading.Thread(target=_am_write, daemon=True).start()


set_memory_recorder(_write_device_memory)


def _presented_token(handler) -> str:
    auth = (handler.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (handler.headers.get("X-Mailbus-Device-Token") or "").strip()


def _client_ip(handler) -> str:
    try:
        return str(handler.client_address[0] or "")
    except Exception:
        return ""


def _resolve_authenticated_device(handler) -> dict:
    bridge_cfg = load_bridge_config(handler.data_dir)
    if not bridge_cfg.get("enabled", True):
        raise DeviceBridgeError("bridge_disabled", 403, "设备桥未启用")
    device = resolve_device(bridge_cfg, _presented_token(handler), _client_ip(handler))
    if not device:
        raise DeviceBridgeError("unauthorized", 401, "设备 token 无效或 IP 不在白名单")
    return device


def _live_agents(handler) -> dict:
    """每次从 config.json 读花名册，避免 UI 新增 agent 后须整进程重启才生效。"""
    from lib.infra.utils import json_read

    cfg = json_read(f"{handler.data_dir}/config.json", {})
    live = cfg.get("agents") if isinstance(cfg.get("agents"), dict) else None
    if live:
        try:
            handler.agents = live
        except Exception:
            pass
        return live
    return getattr(handler, "agents", None) or {}


def _live_agent_types(handler) -> dict:
    return getattr(handler, "agent_types", None) or {}


def _read_device_chat_body(handler) -> dict:
    """读取设备请求体，容忍 chunked / 智能引号 / form-urlencoded / query 参数。

    iOS Postman 常因智能标点把 " 变成 “”，或 body 类型选成 form-data 导致
    JSON 解析失败而丢 text；这里做兜底归一化。
    """
    from urllib.parse import parse_qs, urlparse

    result: dict = {}

    # 1) query 参数兜底
    qs = parse_qs(urlparse(handler.path).query)
    for k, v in qs.items():
        if v:
            result[k] = v[0]

    # 2) body
    raw = b""
    try:
        clen = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        clen = 0
    if clen > 0:
        raw = handler.rfile.read(clen)
    elif (handler.headers.get("Transfer-Encoding") or "").lower() == "chunked":
        while True:
            line = handler.rfile.readline().strip()
            try:
                size = int(line, 16)
            except ValueError:
                break
            if size == 0:
                handler.rfile.readline()
                break
            raw += handler.rfile.read(size)
            handler.rfile.readline()

    if raw:
        text = raw.decode("utf-8", errors="replace")
        ctype = (handler.headers.get("Content-Type") or "").lower()

        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None

        if not isinstance(parsed, dict):
            # 智能标点/全角标点容错（iOS 输入法常见）：
            # 弯引号需手动转直引号（NFKC 不覆盖），全角标点（，：；（）【】等）交给 NFKC
            import unicodedata
            normalized = (
                text.replace("\u201c", '"')
                .replace("\u201d", '"')
                .replace("\u2018", "'")
                .replace("\u2019", "'")
            )
            normalized = unicodedata.normalize("NFKC", normalized)
            try:
                parsed = json.loads(normalized)
            except json.JSONDecodeError:
                parsed = None

        if isinstance(parsed, dict):
            result.update(parsed)
        elif "form-urlencoded" in ctype:
            for k, v in parse_qs(text).items():
                if v:
                    result[k] = v[0]

    return result


def _wants_stream(handler, body: dict) -> bool:
    if body.get("stream") is True or str(body.get("stream") or "").strip().lower() in ("1", "true", "yes"):
        return True
    accept = (handler.headers.get("Accept") or "").lower()
    return "text/event-stream" in accept


def _send_sse(handler, event: str, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    chunk = f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
    handler.wfile.write(chunk)
    handler.wfile.flush()


def _begin_sse(handler) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    # 一轮一答：发完即关。声明 close 让客户端（尤其 Postman/iOS）明确响应边界，
    # 否则 HTTP/1.1 下无 Content-Length 会一直等，表现为「无返回」。
    handler.send_header("Connection", "close")
    if hasattr(handler, "_apply_cors_headers"):
        handler._apply_cors_headers()
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()


def _end_sse(handler) -> None:
    """SSE 流结束：推终止事件并关闭连接。"""
    try:
        _send_sse(handler, "done", {"status": "done"})
    except Exception:
        pass
    try:
        handler.wfile.flush()
    except Exception:
        pass
    handler.close_connection = True


def handle_device_chat(handler):
    try:
        device = _resolve_authenticated_device(handler)
    except DeviceBridgeError as exc:
        handler._send_api_error(exc.code, exc.status, detail=exc.detail)
        return

    body = _read_device_chat_body(handler)
    if not isinstance(body, dict):
        body = {}
    action = str(body.get("action") or "chat").strip().lower()
    if action != "chat":
        handler._send_api_error(
            "unsupported_action", 400,
            detail=f"不支持的 action: {action!r}（通讯用 POST /api/device/chat；建工单用 POST /api/device/task）",
        )
        return

    text = str(body.get("text") or "").strip()
    session_id = str(body.get("session_id") or "").strip()
    if not session_id:
        import uuid

        session_id = uuid.uuid4().hex
    source = body.get("source") if isinstance(body.get("source"), dict) else {}

    bridge_cfg = load_bridge_config(handler.data_dir)
    wait_ms = int(bridge_cfg.get("default_wait_ms") or 8000)
    stream = _wants_stream(handler, body)

    if stream:
        _begin_sse(handler)

        def on_event(event: str, data: dict) -> None:
            _send_sse(handler, event, data)

        try:
            deliver_and_wait(
                handler.data_dir,
                _live_agents(handler),
                _live_agent_types(handler),
                device,
                text,
                session_id,
                wait_ms,
                source,
                on_event=on_event,
            )
        except DeviceBridgeError as exc:
            _send_sse(handler, "error", {"error_code": exc.code, "error": exc.detail or exc.code})
        except BrokenPipeError:
            pass
        except Exception as exc:
            try:
                _send_sse(handler, "error", {"error_code": "stream_error", "error": str(exc)})
            except Exception:
                pass
        _end_sse(handler)
        return

    try:
        result = deliver_and_wait(
            handler.data_dir,
            _live_agents(handler),
            _live_agent_types(handler),
            device,
            text,
            session_id,
            wait_ms,
            source,
        )
    except DeviceBridgeError as exc:
        handler._send_api_error(exc.code, exc.status, detail=exc.detail)
        return

    handler._send_json(result)


def device_body_to_envelope(device: dict, body: dict) -> dict:
    """设备工单请求 → A2A Envelope。默认 explicit 单步，pin 到设备绑定的 agent。"""
    import uuid

    text = str(body.get("intent") or body.get("text") or body.get("summary") or "").strip()
    raw_id = str(body.get("task_id") or "").strip()
    if not raw_id:
        did = str(device.get("id") or "device").replace(" ", "-")
        raw_id = f"dev-{did}-{uuid.uuid4().hex[:12]}"
    pin = str(body.get("pin_agent") or device.get("agent_id") or "").strip()
    mode = str(body.get("mode") or "").strip().lower()
    planned = body.get("planned_chain")
    if isinstance(planned, list) and planned:
        mode = "explicit"
        if pin and isinstance(planned[0], dict) and not planned[0].get("pin_agent"):
            planned = [{**planned[0], "pin_agent": pin}, *planned[1:]]
    elif mode == "auto":
        planned = None
    else:
        mode = "explicit"
        try:
            rt = int(body["role_type"]) if body.get("role_type") is not None else 1
        except (TypeError, ValueError):
            rt = 1
        step: dict = {"role_type": rt, "reason": "device_bridge"}
        if pin:
            step["pin_agent"] = pin
        planned = [step]
    tier = str(body.get("tier") or "S").strip().upper() or "S"
    if tier not in ("S", "M", "L"):
        tier = "S"
    envelope: dict = {
        "task_id": raw_id,
        "intent": text,
        "initiator": f"device:{device.get('id') or 'unknown'}",
        "mode": mode,
        "tier": tier,
        "task_type": str(body.get("task_type") or "feature").strip() or "feature",
        "extensions": {
            "device_bridge": {
                "device_id": device.get("id"),
                "agent_id": device.get("agent_id"),
                "source": body.get("source") if isinstance(body.get("source"), dict) else {},
            }
        },
    }
    if pin:
        envelope["pin_agent"] = pin
    if mode == "explicit" and planned:
        envelope["planned_chain"] = planned
    return envelope


def handle_device_task(handler):
    """POST /api/device/task — 设备鉴权后按 Envelope 创建 pipeline 工单。"""
    try:
        device = _resolve_authenticated_device(handler)
    except DeviceBridgeError as exc:
        handler._send_api_error(exc.code, exc.status, detail=exc.detail)
        return

    body = _read_device_chat_body(handler)
    if not isinstance(body, dict):
        body = {}
    text = str(body.get("intent") or body.get("text") or body.get("summary") or "").strip()
    if not text:
        handler._send_api_error("empty_text", 400, detail="缺少 intent/text")
        return

    envelope = device_body_to_envelope(device, body)
    resp, status = create_task_from_envelope(handler.data_dir, envelope)
    handler._send_json(resp, status)


def handle_device_ticket(handler, ticket_id: str):
    try:
        device = _resolve_authenticated_device(handler)
    except DeviceBridgeError as exc:
        handler._send_api_error(exc.code, exc.status, detail=exc.detail)
        return

    try:
        result = resolve_ticket(handler.data_dir, ticket_id)
    except DeviceBridgeError as exc:
        handler._send_api_error(exc.code, exc.status, detail=exc.detail)
        return

    handler._send_json(result)


def _metis_bridge_cfg(handler) -> dict:
    """读取灵珠/Rokid 端点配置（rokid_ak / rokid_agent_id / rokid_wait_ms）。"""
    bridge_cfg = load_bridge_config(handler.data_dir)
    return {
        "ak": str(bridge_cfg.get("rokid_ak") or "").strip(),
        "agent_id": str(bridge_cfg.get("rokid_agent_id") or "").strip(),
        "wait_ms": int(bridge_cfg.get("rokid_wait_ms") or bridge_cfg.get("default_wait_ms") or 45000),
    }


def _metis_ak_valid(handler, expected_ak: str) -> bool:
    """灵珠 AK 校验（未配置则放行，仅内网调试用）。"""
    if not expected_ak:
        return True
    auth = (handler.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() == expected_ak
    return auth == expected_ak


def _send_metis_sse(handler, event: str, data) -> None:
    """灵珠 SSE 帧：event:xxx\ndata:xxx\n\n（无空格，对齐 Rokid 官方格式）。"""
    data_str = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    handler.wfile.write(f"event:{event}\ndata:{data_str}\n\n".encode("utf-8"))
    handler.wfile.flush()


def handle_metis_sse(handler):
    """灵珠平台自定义智能体 SSE 端点（Rokid 眼镜上游）。

    POST /metis/agent/api/sse
    鉴权: Authorization: Bearer <rokid_ak>
    请求: {message_id, agent_id, message:[{role,type,text}], user_id?, metadata?}
    响应: 灵珠 SSE（message 事件 answer_stream 增量 + done 事件 [DONE]）。
    """
    cfg = _metis_bridge_cfg(handler)
    if not cfg["agent_id"]:
        handler._send_api_error("metis_disabled", 403, detail="灵珠端点未配置 rokid_agent_id")
        return
    if not _metis_ak_valid(handler, cfg["ak"]):
        handler._send_api_error("unauthorized", 401, detail="灵珠 AK 无效")
        return

    body = _read_device_chat_body(handler)
    if not isinstance(body, dict) or not body.get("message_id") or not isinstance(body.get("message"), list):
        handler._send_api_error("bad_request", 400, detail="缺少 message_id / message 数组")
        return

    metis_msg_id = str(body.get("message_id") or "").strip()
    metis_agent_id = str(body.get("agent_id") or "").strip()
    text = ""
    for m in body.get("message") or []:
        if isinstance(m, dict) and m.get("text"):
            text += str(m.get("text")) + "\n"
    text = text.strip()
    if not text:
        handler._send_api_error("empty_text", 400, detail="缺少文本内容")
        return

    import uuid as _uuid

    device = {"id": "rokid-glasses", "agent_id": cfg["agent_id"]}
    session_id = _uuid.uuid4().hex

    _begin_sse(handler)

    def on_event(event: str, data: dict) -> None:
        if event == "delta":
            _send_metis_sse(handler, "message", {
                "role": "agent",
                "type": "answer",
                "answer_stream": str(data.get("delta") or ""),
                "message_id": metis_msg_id,
                "agent_id": metis_agent_id,
                "is_finish": False,
            })
        elif event == "ok":
            _send_metis_sse(handler, "message", {
                "role": "agent",
                "type": "answer",
                "answer_stream": "",
                "message_id": metis_msg_id,
                "agent_id": metis_agent_id,
                "is_finish": True,
            })
        elif event == "pending":
            hint = str(data.get("hint") or "等待回复超时，请稍后重试")
            _send_metis_sse(handler, "message", {
                "role": "agent",
                "type": "answer",
                "answer_stream": hint,
                "message_id": metis_msg_id,
                "agent_id": metis_agent_id,
                "is_finish": True,
            })
        elif event == "waiting":
            # 灵珠 SSE 心跳：注释行保活
            try:
                handler.wfile.write(b": heartbeat\n\n")
                handler.wfile.flush()
            except Exception:
                pass
        # accepted / reply_start 忽略

    try:
        deliver_and_wait(
            handler.data_dir,
            _live_agents(handler),
            _live_agent_types(handler),
            device,
            text,
            session_id,
            cfg["wait_ms"],
            {"channel": "rokid", "device": "glasses", "upstream": "lingzhu"},
            on_event=on_event,
        )
    except DeviceBridgeError as exc:
        _send_metis_sse(handler, "message", {
            "role": "agent", "type": "answer",
            "answer_stream": f"[错误] {exc.detail or exc.code}",
            "message_id": metis_msg_id, "agent_id": metis_agent_id, "is_finish": True,
        })
    except BrokenPipeError:
        pass
    except Exception as exc:
        _send_metis_sse(handler, "message", {
            "role": "agent", "type": "answer",
            "answer_stream": f"[错误] {exc}",
            "message_id": metis_msg_id, "agent_id": metis_agent_id, "is_finish": True,
        })

    _send_metis_sse(handler, "done", "[DONE]")
    try:
        handler.wfile.flush()
    except Exception:
        pass
    handler.close_connection = True
