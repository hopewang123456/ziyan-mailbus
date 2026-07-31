"""Stable transport / observability error codes (Wave3 · S3)."""
from __future__ import annotations

# Shared with locale + doctor/clinic messaging
TRANSPORT_RETRYABLE = "transport_retryable"
TRANSPORT_FATAL = "transport_fatal"
TRANSPORT_TIMEOUT = "transport_timeout"
TRANSPORT_HTTP = "transport_http"
TRANSPORT_A2A = "transport_a2a"
TRANSPORT_WEBHOOK = "transport_webhook"
TRANSPORT_FILE_BUS = "transport_file_bus"
TRANSPORT_CHANNEL_UNKNOWN = "transport_channel_unknown"
DELIVERY_FAILED = "delivery_failed"
A2A_FALLBACK = "a2a_fallback"

ALL_TRANSPORT_CODES = (
    TRANSPORT_RETRYABLE,
    TRANSPORT_FATAL,
    TRANSPORT_TIMEOUT,
    TRANSPORT_HTTP,
    TRANSPORT_A2A,
    TRANSPORT_WEBHOOK,
    TRANSPORT_FILE_BUS,
    TRANSPORT_CHANNEL_UNKNOWN,
    DELIVERY_FAILED,
    A2A_FALLBACK,
)
