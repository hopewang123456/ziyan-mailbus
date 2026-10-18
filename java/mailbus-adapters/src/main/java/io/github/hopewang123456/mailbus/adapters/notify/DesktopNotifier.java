package io.github.hopewang123456.mailbus.adapters.notify;

import io.github.hopewang123456.mailbus.ports.Notifier;

import java.util.concurrent.TimeUnit;

/**
 * Desktop notification (python desktop toast counterpart, minimal): Windows
 * toast via PowerShell when BurntToast is present, falling back to the
 * built-in `msg` session dialog — zero third-party dependencies. No-ops on
 * non-Windows hosts (per-channel isolation swallows everything anyway).
 */
public class DesktopNotifier implements Notifier {

    private static final String TOAST_PS = """
            $ErrorActionPreference='SilentlyContinue'
            $t = New-BurntToastNotification -Text '%s','%s' 2>$null
            if (-not $?) { msg * /time:30 '%s' } exit 0
            """;

    @Override
    public void notify(Level level, String title, String body) {
        if (!System.getProperty("os.name", "").toLowerCase().contains("win")) {
            return;
        }
        try {
            String t = sanitize(title), b = sanitize(body);
            Process p = new ProcessBuilder("powershell", "-NoProfile", "-Command",
                            String.format(TOAST_PS, t, b, t))
                    .redirectErrorStream(true).start();
            p.waitFor(15, TimeUnit.SECONDS);
        } catch (Exception ignored) {
            // per-channel isolation
        }
    }

    /** strip single quotes / newlines — the script embeds text verbatim */
    private static String sanitize(String s) {
        return s == null ? "" : s.replace("'", "").replace("\n", " ").replace("\r", "");
    }
}
