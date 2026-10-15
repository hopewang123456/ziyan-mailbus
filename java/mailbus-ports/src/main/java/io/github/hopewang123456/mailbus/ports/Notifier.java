package io.github.hopewang123456.mailbus.ports;

/**
 * Outbound notification channel (python notifier counterpart, M2 slice:
 * webhook + file digest; desktop/smtp follow).
 *
 * Per-channel failure isolation (python M1 lesson): a channel throwing must
 * never break the caller — implementations swallow-and-log their own errors.
 */
public interface Notifier {

    enum Level { INFO, WARN, CRITICAL }

    void notify(Level level, String title, String body);

    /** Composite: fan out with per-channel isolation. */
    static Notifier fanOut(Notifier... channels) {
        return (level, title, body) -> {
            for (Notifier n : channels) {
                try {
                    n.notify(level, title, body);
                } catch (RuntimeException ignored) {
                    // per-channel isolation — one dead channel never blocks the rest
                }
            }
        };
    }
}
