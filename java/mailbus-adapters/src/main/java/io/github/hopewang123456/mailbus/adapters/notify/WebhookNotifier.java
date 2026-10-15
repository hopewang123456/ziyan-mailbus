package io.github.hopewang123456.mailbus.adapters.notify;

import io.github.hopewang123456.mailbus.ports.Notifier;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Clock;
import java.time.Duration;

/**
 * Generic JSON webhook channel (python webhook counterpart): POSTs
 * {"level","title","body","timestamp"} — works with Slack-compatible
 * gateways, DingTalk signed proxies, generic receivers. Timeout-bounded;
 * failures are swallowed per the per-channel isolation contract.
 */
public class WebhookNotifier implements Notifier {

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    private final String url;
    private final Clock clock;

    public WebhookNotifier(String url, Clock clock) {
        this.url = url;
        this.clock = clock;
    }

    @Override
    public void notify(Level level, String title, String body) {
        if (url == null || url.isBlank()) {
            return;
        }
        String json = "{\"level\":\"" + level + "\",\"title\":" + q(title)
                + ",\"body\":" + q(body) + ",\"timestamp\":\"" + java.time.Instant.now(clock) + "\"}";
        try {
            http.send(HttpRequest.newBuilder(URI.create(url))
                            .timeout(Duration.ofSeconds(8))
                            .header("Content-Type", "application/json")
                            .POST(HttpRequest.BodyPublishers.ofString(json)).build(),
                    HttpResponse.BodyHandlers.discarding());
        } catch (Exception e) {
            // per-channel isolation: swallow, never break the patrol loop
        }
    }

    private static String q(String v) {
        return "\"" + (v == null ? "" : v.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")) + "\"";
    }
}
