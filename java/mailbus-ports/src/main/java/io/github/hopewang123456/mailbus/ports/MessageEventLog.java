package io.github.hopewang123456.mailbus.ports;

import java.util.List;

/**
 * Typed lifecycle event log (plan §4, AgentScope borrowing #1): every FSM
 * transition appends an immutable row; trace and audit read the stream,
 * never reconstruct from snapshots.
 */
public interface MessageEventLog {

    record Event(long seq, String msgId, String agent, String kind,
                 String stateFrom, String stateTo, String detail, String createdAt) {}

    void append(String msgId, String agent, String kind,
                String stateFrom, String stateTo, String detail);

    List<Event> eventsOf(String msgId);

    /** Latest events across all messages (patrol digest, ops views). */
    List<Event> latest(int limit);

    // ── scheduler heartbeat (acceptance "scheduler" check) ──

    void heartbeat(String job, boolean ok, String error);

    record Heartbeat(String job, String lastRunAt, boolean ok, String error) {}

    Heartbeat heartbeatOf(String job);
}
