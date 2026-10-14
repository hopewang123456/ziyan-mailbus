package io.github.hopewang123456.mailbus.infra.ids;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Id generation (Python lib/infra UuidIdGenerator counterpart).
 * Message ids stay human-greppable: msg-<8>; monotonic suffix keeps
 * same-second ids sortable in directory listings.
 */
public final class Ids {

    private static final AtomicLong SEQ = new AtomicLong();

    private Ids() {
    }

    public static String newMessageId() {
        return "msg-" + UUID.randomUUID().toString().substring(0, 8);
    }

    public static String newTaskId() {
        return "task-" + Long.toHexString(System.currentTimeMillis()) + "-" + SEQ.incrementAndGet();
    }
}
