# lib.adapters

Concrete adapters: frameworks, plane, config, transport, container, locale, integrations, ops, orchestration, fakes.

## Role

Implement `lib.interfaces` Protocols; Composition Root wires them in `lib.composition`.

## Dependency direction

`interfaces` ← adapters → `domain` / `core` / root modules (temporary)

## Forbidden imports

`lib.application.*` (legacy exceptions noted in layer tests)

## Subpackages

| Package | Overview |
|---------|----------|
| `transport/` | Message / bridge channels |
| `config/` | Config repo / tokens |
| `frameworks/` | Agent framework plugins |
| `container/` | OpenClaw profiles / privilege |
| `ops/` | OpsPort facade |
| `integrations/` | Plugins / ComfyUI / n8n |
| `locale/` | LocalePort + zh dicts |
| `orchestration/` | FSM / budget / gates |
| `fakes/` | Test doubles |
| `plane/` | Host/container planes |
| `results/` | Result / ack store |
| `discovery/` | Agent discovery sources |
| `internal_llm/` | LLM HTTP client adapters |
