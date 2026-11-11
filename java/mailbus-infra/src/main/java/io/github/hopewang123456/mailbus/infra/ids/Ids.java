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

    /**
     * D16 批3：python {@code generate_msg_id()} 同格式 —— {@code msg-YYYYMMDD-NNNNN}
     * （日期取 Asia/Shanghai，序号 = epochMilli % 100000）。写 inbox.json 的消息
     * 必须用这个格式，python 侧 grep/排序/回执链路才认。
     */
    public static String newPythonMessageId(java.time.Instant now) {
        var cst = now.atZone(java.time.ZoneId.of("Asia/Shanghai"));
        long seq = Math.floorMod(now.toEpochMilli(), 100_000L);
        return "msg-" + cst.format(java.time.format.DateTimeFormatter.ofPattern("yyyyMMdd"))
                + "-" + String.format("%05d", seq);
    }

    public static String newTaskId() {
        return "task-" + Long.toHexString(System.currentTimeMillis()) + "-" + SEQ.incrementAndGet();
    }
}
