package io.github.hopewang123456.mailbus.org;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.util.List;

public final class OrgDtos {

    private OrgDtos() {
    }

    public record TeamIn(@NotBlank @Size(max = 64) String name, String teamId) {
    }

    public record TeamOut(String teamId, String name) {
    }

    public record PositionIn(@NotBlank @Size(max = 64) String name, List<String> capabilities,
                             String positionId) {
    }

    public record PositionOut(String positionId, String name, List<String> capabilities) {
    }

    public record SeatUpdateIn(String teamId, String positionId, Double x, Double y, Double rotation) {
    }

    public record OrgSeatOut(String seatId, String floorId, String roomId, double x, double y,
                             double rotation, String teamId, String positionId) {
    }
}
