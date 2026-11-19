package io.github.hopewang123456.mailbus.messaging;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;

public final class MessageDtos {

    private MessageDtos() {
    }

    public record MessageIn(@NotBlank @Size(max = 4000) String body, String recipientId,
                            @Size(max = 32) String kind,
                            @Pattern(regexp = "file_bus|a2a|mcp") String channel) {
    }

    public record MessageOut(String messageId, String senderId, String recipientId, String kind,
                             String body, Instant createdAt, String deliveryStatus,
                             String pairId) {
    }

    public record DeliveryAttemptOut(String messageId, int attemptNo, boolean ok,
                                     String errorCode, String detail, Instant at) {
    }

    public record PullItem(String eventId, String kind, java.util.Map<String, Object> payload,
                           int attempts) {
    }
}
