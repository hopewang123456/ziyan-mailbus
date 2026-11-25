package io.github.hopewang123456.mailbus.collab;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class ScreenDtos {

    private ScreenDtos() {
    }

    public record ScreenRegisterIn(
            @Size(max = 64) String screenId,
            String secret,
            @Size(max = 64) String name,
            String floorId,
            String seatId
    ) {
    }

    public record ScreenRegisterOut(String screenId, String screenSecret, int configVersion) {
    }

    public record ScreenHeartbeatIn(String floorId, String seatId) {
    }

    public record ScreenFocusIn(
            @NotBlank String floorId,
            String seatId
    ) {
    }

    public record ScreenConfigIn(
            @Pattern(regexp = "office|grid|custom") String layoutType,
            @Pattern(regexp = "auto|dark|light") String theme,
            @Pattern(regexp = "1920x1080|3840x2160") String resolution,
            String teamId,
            Map<String, Object> office,
            Map<String, Object> grid,
            Map<String, Object> custom
    ) {
    }

    public record ScreenDraftIn(
            ScreenConfigIn config,
            @Pattern(regexp = "playing|paused") String playState
    ) {
    }

    public record ScreenConfigOut(
            String screenId,
            int configVersion,
            Integer publishedConfigVersion,
            Instant updatedAt,
            String playState,
            ScreenConfigIn config
    ) {
    }

    public record ScreenPublishIn(
            @NotNull @Min(1) Integer expectedConfigVersion
    ) {
    }

    public record ScreenPublishOut(int configVersion, Instant publishedAt) {
    }

    public record ScreenOut(
            String screenId,
            String name,
            String source,
            boolean online,
            Instant lastSeenAt,
            int configVersion,
            Integer publishedConfigVersion,
            boolean teamBound,
            String playState
    ) {
    }

    public record ScreenListOut(List<ScreenOut> items, int total, int limit, int offset) {
    }

    public record PublicScreenConfigOut(
            String screenId,
            int configVersion,
            boolean published,
            String layoutType,
            String theme,
            String resolution,
            boolean teamBound,
            String playState,
            Map<String, Object> office,
            Map<String, Object> grid,
            Map<String, Object> custom
    ) {
    }

    public record ScreenListQuery(
            @Min(1) @Max(500) Integer limit,
            @Min(0) Integer offset
    ) {
    }
}
