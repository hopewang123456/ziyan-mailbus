package io.github.hopewang123456.mailbus.org;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.events.Outbox;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class OrgService {

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final Outbox outbox;
    private final LayoutSeed seed;
    private final ObjectMapper objectMapper;

    public OrgService(JdbcTemplate jdbc, Ids ids, Outbox outbox, LayoutSeed seed,
                      ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.outbox = outbox;
        this.seed = seed;
        this.objectMapper = objectMapper;
    }

    public List<OrgDtos.TeamOut> teams() {
        return jdbc.query("SELECT team_id, name FROM org_teams ORDER BY created_at",
                (row, index) -> new OrgDtos.TeamOut(row.getString("team_id"), row.getString("name")));
    }

    @Transactional
    public OrgDtos.TeamOut createTeam(Actor actor, OrgDtos.TeamIn input) {
        Authz.require(actor, Authz.ORG_MANAGE);
        String name = requireName(input.name(), "团队名称");
        String teamId = input.teamId() == null || input.teamId().isBlank()
                ? ids.next("team") : input.teamId();
        List<OrgDtos.TeamOut> existing = jdbc.query(
                "SELECT team_id, name FROM org_teams WHERE team_id = ?",
                (row, index) -> new OrgDtos.TeamOut(row.getString("team_id"), row.getString("name")),
                teamId);
        if (!existing.isEmpty()) {
            return existing.get(0);
        }
        jdbc.update("INSERT INTO org_teams (team_id, name, created_at) VALUES (?, ?, ?)",
                teamId, name, Instant.now().getEpochSecond());
        outbox.enqueue("org.team_created", Map.of("team_id", teamId, "name", name));
        return new OrgDtos.TeamOut(teamId, name);
    }

    /** 删除团队：仍被工位或在册员工引用时拒绝，避免布局出现悬空归属。 */
    @Transactional
    public void deleteTeam(Actor actor, String teamId) {
        Authz.require(actor, Authz.ORG_MANAGE);
        requireExists("org_teams", "team_id", teamId, "团队不存在");
        requireNoSeatReference("team_id", teamId, "团队仍被工位引用，请先解除工位归属");
        requireNoEmployeeReference("team_id", teamId, "团队仍被员工引用，请先调整员工归属");
        jdbc.update("""
                UPDATE identity_employees SET team_id = NULL
                 WHERE team_id = ? AND status = 'deregistered'
                """, teamId);
        jdbc.update("DELETE FROM org_teams WHERE team_id = ?", teamId);
        outbox.enqueue("org.team_deleted", Map.of("team_id", teamId));
    }

    /** 删除岗位：仍被工位或在册员工引用时拒绝。 */
    @Transactional
    public void deletePosition(Actor actor, String positionId) {
        Authz.require(actor, Authz.ORG_MANAGE);
        requireExists("org_positions", "position_id", positionId, "岗位不存在");
        requireNoSeatReference("position_id", positionId, "岗位仍被工位引用，请先解除工位归属");
        requireNoEmployeeReference("position_id", positionId, "岗位仍被员工引用，请先调整员工归属");
        jdbc.update("""
                UPDATE identity_employees SET position_id = NULL
                 WHERE position_id = ? AND status = 'deregistered'
                """, positionId);
        jdbc.update("DELETE FROM org_positions WHERE position_id = ?", positionId);
        outbox.enqueue("org.position_deleted", Map.of("position_id", positionId));
    }

    private void requireExists(String table, String column, String id, String message) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table + " WHERE " + column + " = ?",
                Integer.class, id);
        if (count == null || count == 0) {
            throw ApiException.notFound(message);
        }
    }

    private void requireNoSeatReference(String column, String id, String message) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM org_seats WHERE " + column + " = ?",
                Integer.class, id);
        if (count != null && count > 0) {
            throw ApiException.conflict("invalid_state", message);
        }
    }

    private void requireNoEmployeeReference(String column, String id, String message) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM identity_employees WHERE " + column
                        + " = ? AND status <> 'deregistered'",
                Integer.class, id);
        if (count != null && count > 0) {
            throw ApiException.conflict("invalid_state", message);
        }
    }

    public List<OrgDtos.PositionOut> positions() {
        return jdbc.query("SELECT * FROM org_positions ORDER BY created_at",
                (row, index) -> new OrgDtos.PositionOut(
                        row.getString("position_id"), row.getString("name"),
                        parseCaps(row.getString("capabilities"))));
    }

    @Transactional
    public OrgDtos.PositionOut createPosition(Actor actor, OrgDtos.PositionIn input) {
        Authz.require(actor, Authz.ORG_MANAGE);
        String name = requireName(input.name(), "岗位名称");
        String positionId = input.positionId() == null || input.positionId().isBlank()
                ? ids.next("pos") : input.positionId();
        List<OrgDtos.PositionOut> existing = jdbc.query(
                "SELECT * FROM org_positions WHERE position_id = ?",
                (row, index) -> new OrgDtos.PositionOut(
                        row.getString("position_id"), row.getString("name"),
                        parseCaps(row.getString("capabilities"))),
                positionId);
        if (!existing.isEmpty()) {
            return existing.get(0);
        }
        List<String> capabilities = input.capabilities() == null ? List.of()
                : input.capabilities().stream().distinct().sorted().toList();
        jdbc.update("""
                INSERT INTO org_positions (position_id, name, capabilities, created_at)
                VALUES (?, ?, ?, ?)
                """, positionId, name, json(capabilities), Instant.now().getEpochSecond());
        outbox.enqueue("org.position_created", Map.of("position_id", positionId));
        return new OrgDtos.PositionOut(positionId, name, capabilities);
    }

    public List<OrgDtos.OrgSeatOut> seats() {
        Map<String, SeatOverride> overrides = overrides();
        List<OrgDtos.OrgSeatOut> result = new ArrayList<>();
        for (LayoutSeed.Floor floor : seed.site().floors()) {
            for (LayoutSeed.Room room : floor.rooms()) {
                for (LayoutSeed.Seat seat : room.seats()) {
                    SeatOverride override = overrides.get(seat.seatId());
                    result.add(new OrgDtos.OrgSeatOut(
                            seat.seatId(), floor.floorId(), room.roomId(),
                            override != null && override.x() != null ? override.x() : seat.x(),
                            override != null && override.y() != null ? override.y() : seat.y(),
                            override != null && override.rotation() != null
                                    ? override.rotation() : seat.rotation(),
                            override == null ? null : override.teamId(),
                            override == null ? null : override.positionId()));
                }
            }
        }
        return result;
    }

    @Transactional
    public OrgDtos.OrgSeatOut updateSeat(Actor actor, String seatId, OrgDtos.SeatUpdateIn input) {
        Authz.require(actor, Authz.ORG_MANAGE);
        LayoutSeed.Seat seat = seed.site().seat(seatId)
                .orElseThrow(() -> ApiException.notFound("工位不存在"));
        SeatOverride existing = overrides().get(seatId);
        String teamId = input.teamId() != null ? input.teamId()
                : existing == null ? null : existing.teamId();
        String positionId = input.positionId() != null ? input.positionId()
                : existing == null ? null : existing.positionId();
        Double x = input.x() != null ? input.x() : existing == null ? null : existing.x();
        Double y = input.y() != null ? input.y() : existing == null ? null : existing.y();
        Double rotation = input.rotation() != null ? input.rotation()
                : existing == null ? null : existing.rotation();
        jdbc.update("""
                INSERT INTO org_seats (seat_id, team_id, position_id, x, y, rotation, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (seat_id) DO UPDATE SET
                    team_id = excluded.team_id, position_id = excluded.position_id,
                    x = excluded.x, y = excluded.y, rotation = excluded.rotation,
                    updated_at = excluded.updated_at
                """, seatId, teamId, positionId, x, y, rotation, Instant.now().getEpochSecond());
        String[] location = seed.site().locate(seatId).orElse(new String[]{"", ""});
        return new OrgDtos.OrgSeatOut(seatId, location[0], location[1],
                x == null ? seat.x() : x, y == null ? seat.y() : y,
                rotation == null ? seat.rotation() : rotation, teamId, positionId);
    }

    public boolean seatExists(String seatId) {
        return seatId != null && seed.site().hasSeat(seatId);
    }

    public Optional<String> positionForSeat(String seatId) {
        if (seatId == null) {
            return Optional.empty();
        }
        List<String> rows = jdbc.queryForList(
                "SELECT position_id FROM org_seats WHERE seat_id = ? AND position_id IS NOT NULL",
                String.class, seatId);
        return rows.stream().findFirst();
    }

    public List<String> positionCapabilities(String positionId) {
        if (positionId == null) {
            return List.of();
        }
        List<String> rows = jdbc.queryForList(
                "SELECT capabilities FROM org_positions WHERE position_id = ?",
                String.class, positionId);
        return rows.isEmpty() ? List.of() : parseCaps(rows.get(0));
    }

    private Map<String, SeatOverride> overrides() {
        Map<String, SeatOverride> map = new LinkedHashMap<>();
        jdbc.query("SELECT * FROM org_seats", row -> {
            map.put(row.getString("seat_id"), new SeatOverride(
                    row.getString("seat_id"), row.getString("team_id"),
                    row.getString("position_id"), nullableDouble(row, "x"),
                    nullableDouble(row, "y"), nullableDouble(row, "rotation")));
        });
        return map;
    }

    private Double nullableDouble(java.sql.ResultSet row, String column) throws java.sql.SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : value;
    }

    private String requireName(String value, String label) {
        String name = value == null ? "" : value.strip();
        if (name.isEmpty()) {
            throw ApiException.conflict("invalid_state", label + "不能为空");
        }
        if (name.length() > 64) {
            throw ApiException.conflict("invalid_state", label + "不能超过 64 个字符");
        }
        return name;
    }

    private List<String> parseCaps(String value) {
        try {
            return objectMapper.readValue(value == null ? "[]" : value,
                    new TypeReference<List<String>>() {
                    });
        } catch (Exception exception) {
            return List.of();
        }
    }

    private String json(List<String> values) {
        try {
            return objectMapper.writeValueAsString(values);
        } catch (Exception exception) {
            return "[]";
        }
    }

    private record SeatOverride(String seatId, String teamId, String positionId,
                                Double x, Double y, Double rotation) {
    }
}
