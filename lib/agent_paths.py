"""Agent path helpers — thin facade so application does not import adapters.frameworks."""
from __future__ import annotations


def store_path_for_agent(*args, **kwargs):
    from lib.adapters.frameworks import store_path_for_agent as _impl

    return _impl(*args, **kwargs)


def type_supports_auto_ack(*args, **kwargs):
    from lib.adapters.frameworks import type_supports_auto_ack as _impl

    return _impl(*args, **kwargs)
