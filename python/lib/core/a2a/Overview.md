# lib.core.a2a

A2A transport types, HTTP/file bus glue, mapper, router (formerly `lib.transport`).

## Role

Implement A2A JSON-RPC send/stream/poll/cancel and file-bus fallback helpers.

## Dependency direction

→ `domain`, utils; used by `adapters.transport.http_a2a`, `application` poll paths

## Forbidden imports

`lib.api.*`; avoid `adapters.frameworks`

## Files

| File | Purpose |
|------|---------|
| `a2a_standard.py` | `A2ATransport` |
| `http_a2a.py` | HTTP client |
| `file_bus.py` | File-bus A2A path |
| `router.py` | Transport router |
| `dispatch_integration.py` | Message port integration |
| `a2a_cancel.py` / `a2a_stream.py` | Cancel / stream |
| `types.py` / `config.py` / `errors.py` | Shared types |
