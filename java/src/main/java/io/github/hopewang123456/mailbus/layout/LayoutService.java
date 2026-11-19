package io.github.hopewang123456.mailbus.layout;

import io.github.hopewang123456.mailbus.agents.Agent;
import io.github.hopewang123456.mailbus.agents.AgentRepository;
import io.github.hopewang123456.mailbus.identity.Employee;
import io.github.hopewang123456.mailbus.identity.EmployeeRepository;
import io.github.hopewang123456.mailbus.org.LayoutSeed;
import io.github.hopewang123456.mailbus.workflow.TaskDtos;
import io.github.hopewang123456.mailbus.workflow.TaskService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
public class LayoutService {

    private static final Set<String> BUSY_TASKS = Set.of("queued", "running", "blocked");
    private static final Set<String> DONE_NODES = Set.of("done", "skipped");

    private final JdbcTemplate jdbc;
    private final LayoutSeed seed;
    private final EmployeeRepository employees;
    private final AgentRepository agents;
    private final TaskService tasks;

    public LayoutService(JdbcTemplate jdbc, LayoutSeed seed, EmployeeRepository employees,
                         AgentRepository agents, TaskService tasks) {
        this.jdbc = jdbc;
        this.seed = seed;
        this.employees = employees;
        this.agents = agents;
        this.tasks = tasks;
    }

    public LayoutDtos.OfficeSiteOut get() {
        Map<String, SeatOverride> overrides = overrides();
        Map<String, String> teamNames = teamNames();
        Map<String, String> positionNames = positionNames();
        Map<String, Employee> occupants = new LinkedHashMap<>();
        for (Employee employee : employees.listAll()) {
            if (employee.seatId() != null && !"deregistered".equals(employee.status())) {
                occupants.put(employee.seatId(), employee);
            }
        }
        Map<String, Agent> agentMap = new LinkedHashMap<>();
        for (Agent agent : agents.listAll()) {
            agentMap.put(agent.agentId(), agent);
        }
        Map<String, TaskDtos.TaskOut> busy = busyTasks();
        List<LayoutDtos.LayoutFloorOut> floors = new ArrayList<>();
        for (LayoutSeed.Floor floor : seed.site().floors()) {
            List<LayoutDtos.LayoutRoomOut> rooms = new ArrayList<>();
            for (LayoutSeed.Room room : floor.rooms()) {
                List<LayoutDtos.LayoutSeatOut> seats = new ArrayList<>();
                for (LayoutSeed.Seat seat : room.seats()) {
                    SeatOverride override = overrides.get(seat.seatId());
                    Employee occupant = occupants.get(seat.seatId());
                    double x = override != null && override.x() != null ? override.x() : seat.x();
                    double y = override != null && override.y() != null ? override.y() : seat.y();
                    double rotation = override != null && override.rotation() != null
                            ? override.rotation() : seat.rotation();
                    LayoutDtos.SeatAgentOut agent = occupant == null ? null
                            : agentView(occupant, teamNames, positionNames,
                            busy.get(occupant.employeeId()), agentMap.get(occupant.agentId()),
                            override);
                    seats.add(new LayoutDtos.LayoutSeatOut(seat.seatId(), x, y, rotation, agent));
                }
                rooms.add(new LayoutDtos.LayoutRoomOut(room.roomId(), room.name(), room.kind(),
                        room.x(), room.y(), room.w(), room.h(), seats));
            }
            floors.add(new LayoutDtos.LayoutFloorOut(floor.floorId(), floor.name(),
                    floor.level(), rooms));
        }
        return new LayoutDtos.OfficeSiteOut(seed.site().siteId(), seed.site().name(),
                seed.site().orgName(), floors);
    }

    public LayoutDtos.PublicOfficeSiteOut getPublic() {
        LayoutDtos.OfficeSiteOut site = get();
        List<LayoutDtos.PublicLayoutFloorOut> floors = new ArrayList<>();
        for (LayoutDtos.LayoutFloorOut floor : site.floors()) {
            List<LayoutDtos.PublicLayoutRoomOut> rooms = new ArrayList<>();
            for (LayoutDtos.LayoutRoomOut room : floor.rooms()) {
                List<LayoutDtos.PublicLayoutSeatOut> seats = new ArrayList<>();
                for (LayoutDtos.LayoutSeatOut seat : room.seats()) {
                    LayoutDtos.SeatAgentOut agent = seat.agent();
                    LayoutDtos.PublicSeatAgentOut publicAgent = agent == null ? null
                            : new LayoutDtos.PublicSeatAgentOut(agent.displayName(),
                            agent.position(), agent.team(), agent.status(), agent.task(),
                            agent.agentName(), agent.agentFramework(), agent.taskState(),
                            agent.currentNode(), agent.nodeState(), agent.progressDone(),
                            agent.progressTotal());
                    seats.add(new LayoutDtos.PublicLayoutSeatOut(seat.seatId(), seat.x(),
                            seat.y(), seat.rotation(), publicAgent));
                }
                rooms.add(new LayoutDtos.PublicLayoutRoomOut(room.roomId(), room.name(),
                        room.kind(), room.x(), room.y(), room.w(), room.h(), seats));
            }
            floors.add(new LayoutDtos.PublicLayoutFloorOut(floor.floorId(), floor.name(),
                    floor.level(), rooms));
        }
        return new LayoutDtos.PublicOfficeSiteOut(site.siteId(), site.name(),
                site.orgName(), floors);
    }

    private LayoutDtos.SeatAgentOut agentView(Employee employee, Map<String, String> teamNames,
                                              Map<String, String> positionNames,
                                              TaskDtos.TaskOut task, Agent agent,
                                              SeatOverride override) {
        String status = "active".equals(employee.status()) ? "online"
                : "offline".equals(employee.status()) ? "offline" : "offline";
        if (!"offline".equals(status) && task != null) {
            status = "busy";
        }
        String teamId = employee.teamId() != null ? employee.teamId()
                : override == null ? null : override.teamId();
        String positionId = employee.positionId() != null ? employee.positionId()
                : override == null ? null : override.positionId();
        String taskId = "";
        String taskState = "";
        String currentNode = "";
        String nodeState = "";
        int done = 0;
        int total = 0;
        if (task != null) {
            TaskDtos.TaskNodeOut current = currentNode(task);
            done = (int) task.nodes().stream()
                    .filter(node -> DONE_NODES.contains(node.state())).count();
            total = task.nodes().size();
            taskId = task.taskId();
            taskState = task.state();
            currentNode = current == null ? "" : current.name();
            nodeState = current == null ? "" : current.state();
        }
        return new LayoutDtos.SeatAgentOut(
                employee.employeeId(), employee.displayName(),
                positionNames.getOrDefault(positionId == null ? "" : positionId, ""),
                teamNames.getOrDefault(teamId == null ? "" : teamId, ""),
                status, task == null ? "" : task.title(),
                employee.lastHeartbeat() == null ? "" : employee.lastHeartbeat().toString(),
                employee.agentId() == null ? "" : employee.agentId(),
                agent == null ? "" : agent.name(),
                agent == null ? "" : agent.framework(),
                taskId, taskState, currentNode, nodeState, done, total);
    }

    private TaskDtos.TaskNodeOut currentNode(TaskDtos.TaskOut task) {
        for (String state : List.of("running", "dispatched", "blocked")) {
            for (TaskDtos.TaskNodeOut node : task.nodes()) {
                if (state.equals(node.state())) {
                    return node;
                }
            }
        }
        for (TaskDtos.TaskNodeOut node : task.nodes()) {
            if ("pending".equals(node.state())) {
                return node;
            }
        }
        return task.nodes().isEmpty() ? null : task.nodes().get(task.nodes().size() - 1);
    }

    private Map<String, TaskDtos.TaskOut> busyTasks() {
        Map<String, TaskDtos.TaskOut> busy = new LinkedHashMap<>();
        for (TaskDtos.TaskOut task : tasks.list(null, null)) {
            if (task.ownerId() != null && BUSY_TASKS.contains(task.state())) {
                busy.putIfAbsent(task.ownerId(), task);
            }
        }
        return busy;
    }

    private Map<String, String> teamNames() {
        Map<String, String> names = new LinkedHashMap<>();
        jdbc.query("SELECT team_id, name FROM org_teams",
                row -> {
                    names.put(row.getString("team_id"), row.getString("name"));
                });
        return names;
    }

    private Map<String, String> positionNames() {
        Map<String, String> names = new LinkedHashMap<>();
        jdbc.query("SELECT position_id, name FROM org_positions",
                row -> {
                    names.put(row.getString("position_id"), row.getString("name"));
                });
        return names;
    }

    private Map<String, SeatOverride> overrides() {
        Map<String, SeatOverride> map = new LinkedHashMap<>();
        jdbc.query("SELECT * FROM org_seats", row -> {
            map.put(row.getString("seat_id"),
                    new SeatOverride(row.getString("seat_id"), row.getString("team_id"),
                            row.getString("position_id"), nullableDouble(row, "x"),
                            nullableDouble(row, "y"), nullableDouble(row, "rotation")));
        });
        return map;
    }

    private Double nullableDouble(java.sql.ResultSet row, String column)
            throws java.sql.SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : value;
    }

    private record SeatOverride(String seatId, String teamId, String positionId,
                                Double x, Double y, Double rotation) {
    }
}
