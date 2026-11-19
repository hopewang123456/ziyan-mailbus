package io.github.hopewang123456.mailbus.collab;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;

public final class CollabDtos {

    private CollabDtos() {
    }

    public record PairIn(@NotBlank @Size(max = 64) String partnerId) {
    }

    public record PairOut(String pairId, String initiatorId, String partnerId, String state,
                          Instant createdAt, Instant endedAt) {
    }

    public record CollabMessageIn(@NotBlank @Size(max = 4000) String body,
                                  @NotBlank @Size(max = 64) String pairId,
                                  String recipientId,
                                  @Size(max = 32) String kind,
                                  @Pattern(regexp = "file_bus|a2a|mcp") String channel) {
    }
}
