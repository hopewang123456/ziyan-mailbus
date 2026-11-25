package io.github.hopewang123456.mailbus.identity;

import io.github.hopewang123456.mailbus.agents.Agent;
import io.github.hopewang123456.mailbus.agents.AgentRepository;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 员工对外投影的唯一实现：字段名遵循契约 permissions。 */
@Component
public class EmployeeViews {

    private final AgentRepository agents;

    public EmployeeViews(AgentRepository agents) {
        this.agents = agents;
    }

    public IdentityDtos.EmployeeView view(Employee employee) {
        return view(employee, agentMap().get(employee.agentId()));
    }

    public List<IdentityDtos.EmployeeView> views(List<Employee> employees) {
        Map<String, Agent> agentMap = agentMap();
        return employees.stream()
                .map(employee -> view(employee, agentMap.get(employee.agentId())))
                .toList();
    }

    private IdentityDtos.EmployeeView view(Employee employee, Agent agent) {
        return new IdentityDtos.EmployeeView(
                employee.employeeId(), employee.displayName(), employee.accountType(),
                employee.status(), employee.teamId(), employee.positionId(), employee.seatId(),
                employee.agentId(), agent == null ? null : agent.name(),
                agent == null ? null : agent.framework(),
                employee.capabilities().stream().sorted().toList(),
                employee.dataScope(), employee.fileScope(), employee.endpoint(),
                employee.endpointApproved(), employee.lastHeartbeat());
    }

    private Map<String, Agent> agentMap() {
        Map<String, Agent> map = new LinkedHashMap<>();
        for (Agent agent : agents.listAll()) {
            map.put(agent.agentId(), agent);
        }
        return map;
    }
}
