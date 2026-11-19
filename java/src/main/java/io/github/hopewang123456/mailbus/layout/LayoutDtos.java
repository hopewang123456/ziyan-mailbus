package io.github.hopewang123456.mailbus.layout;

import java.util.List;

public final class LayoutDtos {

    private LayoutDtos() {
    }

    public record SeatAgentOut(String agentId, String displayName, String position, String team,
                               String status, String task, String lastHeartbeat,
                               String boundAgentId, String agentName, String agentFramework,
                               String taskId, String taskState, String currentNode,
                               String nodeState, int progressDone, int progressTotal) {
    }

    public record LayoutSeatOut(String seatId, double x, double y, double rotation,
                                SeatAgentOut agent) {
    }

    public record LayoutRoomOut(String roomId, String name, String kind, double x, double y,
                                double w, double h, List<LayoutSeatOut> seats) {
    }

    public record LayoutFloorOut(String floorId, String name, int level,
                                 List<LayoutRoomOut> rooms) {
    }

    public record OfficeSiteOut(String siteId, String name, String orgName,
                                List<LayoutFloorOut> floors) {
    }

    public record PublicSeatAgentOut(String displayName, String position, String team,
                                     String status, String task, String agentName,
                                     String agentFramework, String taskState,
                                     String currentNode, String nodeState,
                                     int progressDone, int progressTotal) {
    }

    public record PublicLayoutSeatOut(String seatId, double x, double y, double rotation,
                                      PublicSeatAgentOut agent) {
    }

    public record PublicLayoutRoomOut(String roomId, String name, String kind, double x, double y,
                                      double w, double h, List<PublicLayoutSeatOut> seats) {
    }

    public record PublicLayoutFloorOut(String floorId, String name, int level,
                                       List<PublicLayoutRoomOut> rooms) {
    }

    public record PublicOfficeSiteOut(String siteId, String name, String orgName,
                                      List<PublicLayoutFloorOut> floors) {
    }
}
