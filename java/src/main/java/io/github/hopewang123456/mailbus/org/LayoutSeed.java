package io.github.hopewang123456.mailbus.org;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.config.AppProperties;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.util.List;
import java.util.Optional;

@Component
public class LayoutSeed {

    public record Seat(String seatId, double x, double y, double rotation) {
    }

    public record Room(String roomId, String name, String kind, double x, double y,
                       double w, double h, List<Seat> seats) {
    }

    public record Floor(String floorId, String name, int level, List<Room> rooms) {
    }

    public record Site(String siteId, String name, String orgName, List<Floor> floors) {
        public Optional<Seat> seat(String seatId) {
            return floors.stream().flatMap(floor -> floor.rooms().stream())
                    .flatMap(room -> room.seats().stream())
                    .filter(seat -> seat.seatId().equals(seatId))
                    .findFirst();
        }

        public boolean hasSeat(String seatId) {
            return seat(seatId).isPresent();
        }

        public Optional<String[]> locate(String seatId) {
            for (Floor floor : floors) {
                for (Room room : floor.rooms()) {
                    if (room.seats().stream().anyMatch(seat -> seat.seatId().equals(seatId))) {
                        return Optional.of(new String[]{floor.floorId(), room.roomId()});
                    }
                }
            }
            return Optional.empty();
        }

        public Optional<Room> room(String roomId) {
            return floors.stream().flatMap(floor -> floor.rooms().stream())
                    .filter(room -> room.roomId().equals(roomId))
                    .findFirst();
        }

        public Optional<String> floorOfSeat(String seatId) {
            return locate(seatId).map(located -> located[0]);
        }
    }

    private final Site site;

    public LayoutSeed(AppProperties properties, ObjectMapper objectMapper) {
        Site loaded;
        try {
            if (Files.exists(properties.layoutPathFile())) {
                loaded = objectMapper.readValue(properties.layoutPathFile().toFile(), Site.class);
            } else {
                loaded = new Site("site-hq", "Mailbus", "Mailbus", List.of());
            }
        } catch (Exception exception) {
            loaded = new Site("site-hq", "Mailbus", "Mailbus", List.of());
        }
        this.site = loaded;
    }

    public Site site() {
        return site;
    }
}
