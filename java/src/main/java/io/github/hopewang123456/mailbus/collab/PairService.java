package io.github.hopewang123456.mailbus.collab;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.identity.EmployeeRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 结对用例：创建、列表与结束。 */
@Service
public class PairService {

    private final PairRepository repository;
    private final EmployeeRepository employees;
    private final Ids ids;
    private final CollabStreamService stream;

    public PairService(PairRepository repository, EmployeeRepository employees,
                       Ids ids, CollabStreamService stream) {
        this.repository = repository;
        this.employees = employees;
        this.ids = ids;
        this.stream = stream;
    }

    public List<CollabDtos.PairOut> list(Actor actor, String state, int limit) {
        String viewerId = actor.has(Authz.ALL) ? null : actor.employeeId();
        return repository.list(state, viewerId, limit).stream()
                .map(this::view).toList();
    }

    @Transactional
    public CollabDtos.PairOut create(Actor actor, String partnerId) {
        Authz.ensureActive(actor);
        String partner = partnerId == null ? "" : partnerId.strip();
        if (partner.equals(actor.employeeId())) {
            throw ApiException.conflict("invalid_state", "不能与自己结对");
        }
        if (employees.find(partner).isEmpty()) {
            throw ApiException.notFound("员工不存在");
        }
        if (repository.findActiveBetween(actor.employeeId(), partner).isPresent()) {
            throw ApiException.conflict("invalid_state", "双方已存在进行中的结对");
        }
        Instant now = Instant.now();
        PairRepository.Row row = new PairRepository.Row(ids.next("pair"),
                actor.employeeId(), partner, "active", now, null);
        repository.save(row);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("pair_id", row.pairId());
        payload.put("initiator_id", row.initiatorId());
        payload.put("partner_id", row.partnerId());
        payload.put("at", now.toString());
        stream.publish("pair.started", payload);
        return view(row);
    }

    @Transactional
    public void end(Actor actor, String pairId) {
        Authz.ensureActive(actor);
        PairRepository.Row pair = repository.get(pairId)
                .orElseThrow(() -> ApiException.notFound("结对不存在"));
        if (!actor.has(Authz.ALL) && !pair.involves(actor.employeeId())) {
            throw ApiException.forbidden("只能结束自己参与的结对");
        }
        if ("ended".equals(pair.state())) {
            return;
        }
        Instant now = Instant.now();
        repository.save(new PairRepository.Row(pair.pairId(), pair.initiatorId(),
                pair.partnerId(), "ended", pair.createdAt(), now));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("pair_id", pairId);
        payload.put("at", now.toString());
        stream.publish("pair.ended", payload);
    }

    private CollabDtos.PairOut view(PairRepository.Row row) {
        return new CollabDtos.PairOut(row.pairId(), row.initiatorId(), row.partnerId(),
                row.state(), row.createdAt(), row.endedAt());
    }
}
