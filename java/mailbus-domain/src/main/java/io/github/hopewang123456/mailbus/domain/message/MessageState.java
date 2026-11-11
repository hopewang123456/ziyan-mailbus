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
    RECEIVED,
    PROCESSING,
    RESENDING,
    DONE,
    ACKNOWLEDGED,
    REJECTED,
    FAILED,
    CLOSED,
    ARCHIVED,
    SENT;

    /**
     * Terminal states — no further transitions. D16 批2：与 python
     * {@code _TERMINAL_STATES = {done, closed, rejected, failed, archived, sent}}
     * 对齐（未读数口径双栈同源）。注意 python 的 acknowledged 仍是<b>非终态</b>
     * （ack→processing→done 的中间态），故 java ACKNOWLEDGED 不再算终态。
     */
    public boolean isTerminal() {
        return this == DONE || this == REJECTED
                || this == ARCHIVED || this == CLOSED || this == FAILED || this == SENT;
    }

    /**
     * Legal transitions. Throws on illegal moves — the FSM lives here, not in
     * scattered conditionals (complexity stays in deterministic code, not LLM).
     *
     * <p>D16 批2：python 独有状态（received/resending/failed/closed/sent）作为
     * 投影态纳入，转移规则按 python 扫描链路语义补全；写路径仍以 python
     * 状态机为准（D3）。
     */
    public boolean canTransitionTo(MessageState next) {
        return switch (this) {
            case PENDING -> next == PUSHED || next == PROCESSING || next == REJECTED
                    || next == CLOSED;
            case PUSHED -> next == PROCESSING || next == REJECTED || next == PENDING
                    || next == RECEIVED || next == FAILED; // PENDING = re-push fallback
            case RECEIVED -> next == PROCESSING || next == DONE || next == REJECTED
                    || next == PENDING;
            case PROCESSING -> next == DONE || next == REJECTED || next == PENDING
                    || next == FAILED; // stall recovery
            case RESENDING -> next == PUSHED || next == PROCESSING || next == FAILED
                    || next == PENDING;
            case DONE -> next == ACKNOWLEDGED || next == ARCHIVED;
            case ACKNOWLEDGED -> next == PROCESSING || next == DONE || next == REJECTED
                    || next == ARCHIVED;
            case REJECTED, FAILED, CLOSED, ARCHIVED, SENT -> false;
        };
    }
}
