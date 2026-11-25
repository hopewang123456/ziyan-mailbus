package io.github.hopewang123456.mailbus.ops;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

/** 单次通知投递；重试、退避与失败审计由 OpsService 负责。 */
@Component
public class AlertNotifier {

    private static final Duration TIMEOUT = Duration.ofSeconds(5);
    private static final int TIMEOUT_MILLIS = 5_000;

    private final ObjectMapper objectMapper;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(TIMEOUT)
            .followRedirects(HttpClient.Redirect.NORMAL).build();

    public AlertNotifier(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public void send(String channel, String target, Map<String, Object> payload) throws Exception {
        switch (channel) {
            case "inapp" -> {
                // 站内通知即 /api/alerts 中的告警本身。
            }
            case "webhook" -> webhook(target, payload);
            case "email" -> email(target, payload);
            default -> throw new IllegalArgumentException("不支持的通知渠道：" + channel);
        }
    }

    private void webhook(String target, Map<String, Object> payload) throws Exception {
        if (target == null || target.isEmpty()) {
            throw new IllegalArgumentException("webhook 渠道需要 target URL");
        }
        HttpRequest request = HttpRequest.newBuilder(URI.create(target)).timeout(TIMEOUT)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json(payload, false),
                        StandardCharsets.UTF_8)).build();
        HttpResponse<String> response;
        try {
            response = http.send(request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw exception;
        }
        if (response.statusCode() >= 400) {
            throw new IllegalStateException("webhook 返回 " + response.statusCode());
        }
    }

    private void email(String target, Map<String, Object> payload) throws IOException {
        String host = environment("MAILBUS_SMTP_HOST", "").trim();
        if (host.isEmpty()) {
            throw new IllegalStateException("邮件通道未配置 MAILBUS_SMTP_HOST");
        }
        if (target == null || target.isEmpty()) {
            throw new IllegalArgumentException("email 渠道需要接收人地址");
        }
        int port = Integer.parseInt(environment("MAILBUS_SMTP_PORT", "25"));
        String sender = environment("MAILBUS_SMTP_FROM", "mailbus@localhost");
        requireHeaderValue(sender);
        requireHeaderValue(target);

        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), TIMEOUT_MILLIS);
            socket.setSoTimeout(TIMEOUT_MILLIS);
            BufferedReader reader = new BufferedReader(new InputStreamReader(
                    socket.getInputStream(), StandardCharsets.UTF_8));
            BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(
                    socket.getOutputStream(), StandardCharsets.UTF_8));
            expect(reader, 220);
            command(writer, "EHLO localhost");
            if (readResponse(reader) != 250) {
                command(writer, "HELO localhost");
                expect(reader, 250);
            }
            command(writer, "MAIL FROM:<" + sender + ">");
            expect(reader, 250);
            command(writer, "RCPT TO:<" + target + ">");
            expect(reader, 250, 251);
            command(writer, "DATA");
            expect(reader, 354);

            String type = String.valueOf(payload.getOrDefault("type", "alert"));
            StringBuilder message = new StringBuilder()
                    .append("From: ").append(sender).append("\r\n")
                    .append("To: ").append(target).append("\r\n")
                    .append("Subject: [mailbus] ").append(type).append("\r\n")
                    .append("MIME-Version: 1.0\r\n")
                    .append("Content-Type: text/plain; charset=UTF-8\r\n")
                    .append("Content-Transfer-Encoding: 8bit\r\n\r\n")
                    .append(dotStuff(json(payload, true)));
            writer.write(message.toString());
            if (message.length() < 2 || !message.substring(message.length() - 2).equals("\r\n")) {
                writer.write("\r\n");
            }
            writer.write(".\r\n");
            writer.flush();
            expect(reader, 250);
            command(writer, "QUIT");
            expect(reader, 221);
        }
    }

    private String json(Map<String, Object> payload, boolean pretty) {
        try {
            return pretty ? objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(payload)
                    : objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("通知内容序列化失败", exception);
        }
    }

    private static String dotStuff(String body) {
        String normalized = body.replace("\r\n", "\n").replace('\r', '\n');
        String[] lines = normalized.split("\n", -1);
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < lines.length; index++) {
            if (lines[index].startsWith(".")) {
                result.append('.');
            }
            result.append(lines[index]);
            if (index + 1 < lines.length) {
                result.append("\r\n");
            }
        }
        return result.toString();
    }

    private static void command(BufferedWriter writer, String value) throws IOException {
        writer.write(value);
        writer.write("\r\n");
        writer.flush();
    }

    private static void expect(BufferedReader reader, int... accepted) throws IOException {
        int code = readResponse(reader);
        for (int candidate : accepted) {
            if (code == candidate) {
                return;
            }
        }
        throw new IOException("SMTP 返回 " + code);
    }

    private static int readResponse(BufferedReader reader) throws IOException {
        int code = -1;
        while (true) {
            String line = reader.readLine();
            if (line == null || line.length() < 3) {
                throw new IOException("SMTP 响应不完整");
            }
            try {
                code = Integer.parseInt(line.substring(0, 3));
            } catch (NumberFormatException exception) {
                throw new IOException("SMTP 响应不合法", exception);
            }
            if (line.length() < 4 || line.charAt(3) != '-') {
                return code;
            }
        }
    }

    private static String environment(String name, String fallback) {
        String value = System.getenv(name);
        return value == null ? fallback : value;
    }

    private static void requireHeaderValue(String value) {
        if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("SMTP 地址不能包含换行符");
        }
    }
}
