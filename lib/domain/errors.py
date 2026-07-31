"""Domain errors — stable codes for API/locale."""
from __future__ import annotations


class MailbusError(Exception):
    code: str = "mailbus_error"

    def __init__(self, message: str = "", *, code: str | None = None):
        super().__init__(message or self.code)
        if code:
            self.code = code
        self.message = message or self.code


class Retryable(MailbusError):
    code = "retryable"


class Fatal(MailbusError):
    code = "fatal"


class NeedsHuman(MailbusError):
    code = "needs_human"


class LockBusy(Retryable):
    code = "lock_busy"


class Unauthorized(Fatal):
    code = "unauthorized"


class BudgetPaused(NeedsHuman):
    code = "budget_paused"


class EscalationNeeded(NeedsHuman):
    code = "escalation_needed"


# Task pause_reason when budget FSM enters paused_budget (Q8B)
PAUSE_REASON_BUDGET = "budget_exhausted"
