package io.github.hopewang123456.mailbus.domain.message;

/**
 * Message lifecycle FSM — single source of truth for state names.
 *
 * Aligns with the Python implementation's lifecycle (create -> dispatch ->
 * deliver -> execute -> receipt -> accept -> archive) but merges the
 * historical status/state duplication into ONE field (audit L2 remediation:
 * schema discipline — one enum, UTC timestamps, ops metadata separated).
 */
public enum MessageState {
    PENDING,
    PUSHED,
    PROCESSING,
    DONE,
    ACKNOWLEDGED,
    REJECTED,
    ARCHIVED;

    /** Terminal states — no further transitions. */
    public boolean isTerminal() {
        return this == DONE || this == ACKNOWLEDGED || this == REJECTED || this == ARCHIVED;
    }

    /**
     * Legal transitions. Throws on illegal moves — the FSM lives here, not in
     * scattered conditionals (complexity stays in deterministic code, not LLM).
     */
    public boolean canTransitionTo(MessageState next) {
        return switch (this) {
            case PENDING -> next == PUSHED || next == PROCESSING || next == REJECTED;
            case PUSHED -> next == PROCESSING || next == REJECTED || next == PENDING; // PENDING = re-push fallback
            case PROCESSING -> next == DONE || next == REJECTED || next == PENDING;   // stall recovery
            case DONE -> next == ACKNOWLEDGED || next == ARCHIVED;
            case ACKNOWLEDGED -> next == ARCHIVED;
            case REJECTED, ARCHIVED -> false;
        };
    }
}
