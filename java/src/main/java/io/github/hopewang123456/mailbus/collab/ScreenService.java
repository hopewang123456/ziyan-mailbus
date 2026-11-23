package io.github.hopewang123456.mailbus.collab;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 大屏登记、心跳、离线与遥控聚焦。 */
@Service
public class ScreenService {

    private static final Set<String> ADMIN_ACTIONS =
            Set.of(Authz.TASK_DISPATCH, Authz.CONSOLE_ADMIN);
    private static final Duration ONLINE_TTL = Duration.ofSeconds(60);

    private final ScreenRepository repository;
    private final Ids ids;
    private final CollabStreamService stream;

    public ScreenService(ScreenRepository repository, Ids ids,
                         CollabStreamService stream) {
        this.repository = repository;
        this.ids = ids;
        this.stream = stream;
    }

    public List<ScreenDtos.ScreenOut> list() {
        Instant now = Instant.now();
        return repository.listAll().stream().map(row -> view(row, now)).toList();
    }

    @Transactional
    public ScreenDtos.ScreenOut register(Actor actor, ScreenDtos.ScreenIn input) {
        ensureAdmin(actor);
        return upsert(input.screenId(), input.name(), input.floorId(), input.seatId());
    }

    @Transactional
    public ScreenDtos.ScreenOut registerPublic(ScreenDtos.PublicScreenIn input) {
        return upsert(input.screenId(), input.name(), input.floorId(), input.seatId());
    }

    @Transactional
    public void heartbeat(String screenId, String floorId, String seatId) {
        ScreenRepository.Row row = repository.get(screenId)
                .orElseThrow(() -> ApiException.notFound("大屏不存在"));
        repository.save(new ScreenRepository.Row(row.screenId(), row.name(),
                floorId, seatId, true, Instant.now(), row.createdAt()));
    }

    @Transactional
    public void leave(String screenId) {
        repository.get(screenId).ifPresent(row -> repository.save(
                new ScreenRepository.Row(row.screenId(), row.name(), row.floorId(),
                        row.seatId(), false, Instant.now(), row.createdAt())));
    }

    /** 管理端强制下线：不校验大屏密钥，仅要求控制台管理能力。 */
    @Transactional
    public void forceLeave(Actor actor, String screenId) {
        Authz.require(actor, Authz.CONSOLE_ADMIN);
        leave(screenId);
    }

    public void focus(Actor actor, String screenId, String floorId, String seatId) {
        ensureAdmin(actor);
        if (repository.get(screenId).isEmpty()) {
            throw ApiException.notFound("大屏不存在");
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("screen_id", screenId);
        payload.put("floor_id", floorId);
        payload.put("seat_id", seatId);
        payload.put("at", Instant.now().toString());
        stream.publish("screen.focus", payload);
    }

    private ScreenDtos.ScreenOut upsert(String screenId, String name,
                                        String floorId, String seatId) {
        Instant now = Instant.now();
        String actualId = screenId == null || screenId.isBlank()
                ? ids.next("screen") : screenId.strip();
        Instant createdAt = repository.get(actualId)
                .map(ScreenRepository.Row::createdAt).orElse(now);
        repository.save(new ScreenRepository.Row(actualId, name, floorId, seatId,
                true, now, createdAt));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("screen_id", actualId);
        payload.put("name", name);
        payload.put("floor_id", floorId);
        payload.put("at", now.toString());
        stream.publish("screen.registered", payload);
        return view(repository.get(actualId).orElseThrow(), now);
    }

    private ScreenDtos.ScreenOut view(ScreenRepository.Row row, Instant now) {
        boolean fresh = row.lastSeen() != null
                && Duration.between(row.lastSeen(), now).compareTo(ONLINE_TTL) <= 0;
        return new ScreenDtos.ScreenOut(row.screenId(), row.name(), row.floorId(),
                row.seatId(), row.online() && fresh, row.lastSeen());
    }

    private void ensureAdmin(Actor actor) {
        Authz.ensureAnyAllowed(actor, ADMIN_ACTIONS, Authz.Resource.of("screen"));
    }
}
