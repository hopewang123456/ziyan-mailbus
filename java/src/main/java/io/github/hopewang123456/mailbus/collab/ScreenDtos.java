package io.github.hopewang123456.mailbus.collab;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.time.Instant;

public final class ScreenDtos {

    private ScreenDtos() {
    }

    public record ScreenIn(
            @Size(max = 64) String screenId,
            @NotNull @Size(min = 1, max = 64) String name,
            String floorId,
            String seatId
    ) {
    }

    public record PublicScreenIn(
            @NotNull @Size(min = 1, max = 64) String screenId,
            @NotNull @Size(min = 1, max = 64) String name,
            String floorId,
            String seatId
    ) {
    }

    public record ScreenHeartbeatIn(
            String floorId,
            String seatId
    ) {
    }

    public record ScreenFocusIn(
            @NotNull @Size(min = 1) String floorId,
            String seatId
    ) {
    }

    public record ScreenOut(
            String screenId,
            String name,
            String floorId,
            String seatId,
            boolean online,
            Instant lastSeen
    ) {
    }
}
