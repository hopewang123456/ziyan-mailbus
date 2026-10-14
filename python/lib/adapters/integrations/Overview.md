# lib.adapters.integrations

External plugin discovery and third-party integration adapters.

## Role

Implement `IntegrationsPort` and host ComfyUI / n8n / GPU / external tool plugins.

## Dependency direction

`interfaces.IntegrationsPort` ← `port_adapter` → `plugin_registry` / root model_router / ollama / agentmemory

## Forbidden imports

`lib.application.*`

## Files

| File | Purpose |
|------|---------|
| `port_adapter.py` | `PluginIntegrationsAdapter` |
| `plugin_registry.py` | Register / invoke integrations |
| `entry_point_discovery.py` | Entry-point plugin load |
| `comfyui/` `n8n/` `gpu.py` `external_tools.py` | Concrete integrations |
