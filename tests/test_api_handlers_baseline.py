"""Wave7: minimal API handler import / callable baseline."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "module,handler",
    [
        ("lib.api.handlers_system", "handle_status"),
        ("lib.api.handlers_tasks", "handle_tasks"),
        ("lib.api.handlers_inbox", "handle_inbox"),
        ("lib.api.handlers_lifecycle", "handle_mailbus_token"),
        ("lib.api.handlers_settings", "handle_settings_sections"),
    ],
)
def test_api_handlers_callable(module: str, handler: str) -> None:
    import importlib

    mod = importlib.import_module(module)
    fn = getattr(mod, handler, None)
    assert callable(fn), f"{module}.{handler} missing or not callable"
