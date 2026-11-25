package io.github.hopewang123456.mailbus.collab;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 大屏：公开登记/心跳/离线与管理工作流（草稿、发布、聚焦、删除）。 */
@Service
public class ScreenService {

    private static final Set<String> ADMIN_ACTIONS = Set.of(Authz.CONSOLE_ADMIN);
    private static final Duration ONLINE_TTL = Duration.ofSeconds(60);
    private static final List<String> LAYOUT_TYPES = List.of("office", "grid", "custom");
    private static final List<String> THEMES = List.of("auto", "dark", "light");
    private static final List<String> RESOLUTIONS = List.of("1920x1080", "3840x2160");
    private static final List<String> PLAY_STATES = List.of("playing", "paused");

    private final ScreenRepository repository;
    private final Ids ids;
    private final CollabStreamService stream;
    private final ScreenSecretHasher hasher;
    private final ScreenRateLimiter limiter;
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    private final int maxScreens;

    public ScreenService(ScreenRepository repository, Ids ids, CollabStreamService stream,
                         ScreenSecretHasher hasher, ScreenRateLimiter limiter,
                         JdbcTemplate jdbc, ObjectMapper objectMapper,
                         @Value("${mailbus.public-screen-limit:64}") int maxScreens) {
        this.repository = repository;
        this.ids = ids;
        this.stream = stream;
        this.hasher = hasher;
        this.limiter = limiter;
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
        this.maxScreens = maxScreens;
    }

    public ScreenDtos.ScreenListOut listPage(int limit, int offset) {
        Instant now = Instant.now();
        List<ScreenDtos.ScreenOut> items = repository.listPage(limit, offset).stream()
                .map(row -> view(row, now)).toList();
        return new ScreenDtos.ScreenListOut(items, repository.count(), limit, offset);
    }

    public ScreenDtos.ScreenConfigOut config(Actor actor, String screenId) {
        ensureAdmin(actor);
        return configView(require(screenId));
    }

    @Transactional
    public Registered register(String ip, ScreenDtos.ScreenRegisterIn input) {
        ensureAllowed(limiter, "register:" + ip);
        Instant now = Instant.now();
        ScreenRepository.Row reused = reusable(input);
        if (reused != null) {
            ScreenRepository.Row updated = withOnline(reused, true, now);
            repository.save(updated);
            return new Registered(updated, null);
        }
        ensureCapacity(now);
        String secret = ids.next("mbks");
        String name = input.name() == null || input.name().isBlank()
                ? "未命名大屏" : input.name().strip();
        if (name.length() > 64) {
            name = name.substring(0, 64);
        }
        ScreenRepository.Row fresh = new ScreenRepository.Row(ids.next("screen"), name,
                "auto", true, now, now, new LinkedHashMap<>(), new LinkedHashMap<>(),
                1, now, hasher.digest(secret));
        repository.save(fresh);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("screen_id", fresh.screenId());
        payload.put("name", fresh.name());
        payload.put("at", now.toString());
        stream.publish("screen.registered", payload);
        return new Registered(fresh, secret);
    }

    @Transactional
    public void heartbeat(String ip, String screenId, String secret) {
        ensureAllowed(limiter, "heartbeat:" + ip);
        ScreenRepository.Row row = require(screenId);
        ensureSecret(row, secret);
        repository.save(withOnline(row, true, Instant.now()));
    }

    @Transactional
    public void leave(String ip, String screenId, String secret) {
        ensureAllowed(limiter, "leave:" + ip);
        ScreenRepository.Row row = require(screenId);
        ensureSecret(row, secret);
        repository.save(withOnline(row, false, Instant.now()));
    }

    public ScreenDtos.PublicScreenConfigOut publicConfig(String screenId) {
        ScreenRepository.Row row = require(screenId);
        Map<String, Object> config = row.publishedConfig();
        return new ScreenDtos.PublicScreenConfigOut(row.screenId(), row.configVersion(),
                !config.isEmpty(), text(config, "layout_type", "office"),
                text(config, "theme", "auto"), text(config, "resolution", "1920x1080"),
                !config.isEmpty() && text(config, "team_id", "").length() > 0,
                playState(row), section(config, "office"), section(config, "grid"),
                section(config, "custom"));
    }

    public String publishedTeamId(String screenId) {
        if (screenId == null) {
            return null;
        }
        Map<String, Object> config = require(screenId).publishedConfig();
        String teamId = text(config, "team_id", "");
        return teamId.isBlank() ? null : teamId;
    }

    @Transactional
    public ScreenDtos.ScreenConfigOut saveDraft(Actor actor, String screenId,
                                                ScreenDtos.ScreenDraftIn input) {
        ensureAdmin(actor);
        ScreenRepository.Row row = require(screenId);
        Map<String, Object> config = input.config() == null
                ? new LinkedHashMap<>(row.config()) : normalize(input.config());
        if (input.playState() != null) {
            if (config.isEmpty()) {
                config = defaults();
            }
            config.put("play_state", input.playState());
        }
        ScreenRepository.Row updated = new ScreenRepository.Row(row.screenId(), row.name(),
                "manual", row.online(), row.lastSeen(), row.createdAt(), config,
                row.publishedConfig(), row.configVersion(), Instant.now(), row.secretHash());
        repository.save(updated);
        audit(actor, "screen.draft_saved", screenId,
                Map.of("config_version", updated.configVersion()));
        return configView(updated);
    }

    @Transactional
    public ScreenDtos.ScreenPublishOut publish(Actor actor, String screenId,
                                               int expectedVersion) {
        ensureAdmin(actor);
        ScreenRepository.Row row = require(screenId);
        if (expectedVersion != row.configVersion()) {
            throw ApiException.conflict("version_conflict", "屏幕配置已被他人修改，请刷新后重试");
        }
        if (row.config().isEmpty()) {
            throw ApiException.unprocessable("unprocessable", "没有可发布的布局");
        }
        Instant now = Instant.now();
        ScreenRepository.Row updated = new ScreenRepository.Row(row.screenId(), row.name(),
                row.source(), row.online(), row.lastSeen(), row.createdAt(),
                row.config(), new LinkedHashMap<>(row.config()), row.configVersion() + 1,
                now, row.secretHash());
        repository.save(updated);
        audit(actor, "screen.published", screenId,
                Map.of("config_version", updated.configVersion()));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("screen_id", screenId);
        payload.put("config_version", updated.configVersion());
        payload.put("at", now.toString());
        stream.publish("screen.config", payload);
        return new ScreenDtos.ScreenPublishOut(updated.configVersion(), now);
    }

    public void focus(Actor actor, String screenId, String floorId, String seatId) {
        ensureAdmin(actor);
        Instant now = Instant.now();
        ScreenRepository.Row row = require(screenId);
        if (!online(row, now)) {
            throw ApiException.invalid("屏幕离线，无法聚焦");
        }
        audit(actor, "screen.focused", screenId,
                seatId == null ? Map.of("floor_id", floorId)
                        : Map.of("floor_id", floorId, "seat_id", seatId));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("screen_id", screenId);
        payload.put("floor_id", floorId);
        payload.put("seat_id", seatId);
        payload.put("at", now.toString());
        stream.publish("screen.focus", payload);
    }

    @Transactional
    public void delete(Actor actor, String screenId) {
        ensureAdmin(actor);
        ScreenRepository.Row row = require(screenId);
        if (online(row, Instant.now())) {
            throw ApiException.invalid("屏幕正在播放，无法删除");
        }
        repository.delete(screenId);
        audit(actor, "screen.deleted", screenId, Map.of());
    }

    /** 仅清理从未被接管且长期离线的自动登记屏幕。 */
    @Scheduled(fixedDelayString = "${mailbus.screen-prune-interval-ms:3600000}")
    public void pruneStale() {
        Instant cutoff = Instant.now().minus(Duration.ofDays(30));
        for (ScreenRepository.Row row : repository.listAll()) {
            if (!"auto".equals(row.source())) {
                continue;
            }
            Instant seen = row.lastSeen() == null ? row.createdAt() : row.lastSeen();
            if (seen.isBefore(cutoff)) {
                repository.delete(row.screenId());
            }
        }
    }

    // ---- 内部 ----

    private ScreenRepository.Row reusable(ScreenDtos.ScreenRegisterIn input) {
        if (input.screenId() == null || input.screenId().isBlank()
                || input.secret() == null || input.secret().isBlank()) {
            return null;
        }
        return repository.get(input.screenId().strip())
                .filter(row -> hasher.verify(row.secretHash(), input.secret()))
                .orElse(null);
    }

    private void ensureCapacity(Instant now) {
        long online = repository.listAll().stream().filter(row -> online(row, now)).count();
        if (online >= maxScreens) {
            throw ApiException.capacityExceeded("公开大屏数量已达上限，请联系管理员");
        }
    }

    private Map<String, Object> normalize(ScreenDtos.ScreenConfigIn input) {
        Map<String, Object> config = defaults();
        if (input.layoutType() != null) {
            config.put("layout_type", choice(input.layoutType(), LAYOUT_TYPES, "layout_type"));
        }
        if (input.theme() != null) {
            config.put("theme", choice(input.theme(), THEMES, "theme"));
        }
        if (input.resolution() != null) {
            config.put("resolution", choice(input.resolution(), RESOLUTIONS, "resolution"));
        }
        String teamId = input.teamId() == null ? null : input.teamId().strip();
        config.put("team_id", teamId == null || teamId.isEmpty() ? null : teamId);
        if ("grid".equals(config.get("layout_type"))
                && config.get("team_id") == null) {
            throw ApiException.unprocessable("unprocessable", "grid 布局必须绑定团队");
        }
        put(config, "office", input.office());
        put(config, "grid", input.grid());
        put(config, "custom", input.custom());
        return config;
    }

    private static Map<String, Object> defaults() {
        Map<String, Object> config = new LinkedHashMap<>();
        config.put("layout_type", "office");
        config.put("theme", "auto");
        config.put("resolution", "1920x1080");
        config.put("play_state", "playing");
        config.put("team_id", null);
        return config;
    }

    private static void put(Map<String, Object> config, String key, Map<String, Object> value) {
        if (value != null) {
            config.put(key, value);
        }
    }

    private static String choice(String value, List<String> allowed, String key) {
        if (!allowed.contains(value)) {
            throw ApiException.unprocessable("unprocessable", "不支持的 " + key + "：" + value);
        }
        return value;
    }

    private ScreenRepository.Row require(String screenId) {
        return repository.get(screenId)
                .orElseThrow(() -> ApiException.notFound("大屏不存在"));
    }

    private void ensureSecret(ScreenRepository.Row row, String secret) {
        if (!hasher.verify(row.secretHash(), secret)) {
            throw ApiException.forbidden("大屏密钥无效");
        }
    }

    private static void ensureAllowed(ScreenRateLimiter limiter, String key) {
        if (!limiter.allow(key)) {
            throw ApiException.rateLimited("大屏请求过于频繁，请稍后再试");
        }
    }

    private static ScreenRepository.Row withOnline(ScreenRepository.Row row, boolean online,
                                                   Instant now) {
        return new ScreenRepository.Row(row.screenId(), row.name(), row.source(), online,
                now, row.createdAt(), row.config(), row.publishedConfig(),
                row.configVersion(), row.updatedAt(), row.secretHash());
    }

    private static boolean online(ScreenRepository.Row row, Instant now) {
        return row.online() && row.lastSeen() != null
                && Duration.between(row.lastSeen(), now).compareTo(ONLINE_TTL) <= 0;
    }

    private static String playState(ScreenRepository.Row row) {
        Object draft = row.config().get("play_state");
        Object published = row.publishedConfig().get("play_state");
        if (draft != null) {
            return String.valueOf(draft);
        }
        return published == null ? "playing" : String.valueOf(published);
    }

    private static String text(Map<String, Object> config, String key, String fallback) {
        Object value = config.get(key);
        return value == null ? fallback : String.valueOf(value);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> section(Map<String, Object> config, String key) {
        Object value = config.get(key);
        return value instanceof Map<?, ?> map ? (Map<String, Object>) map : null;
    }

    private ScreenDtos.ScreenOut view(ScreenRepository.Row row, Instant now) {
        boolean published = !row.publishedConfig().isEmpty();
        return new ScreenDtos.ScreenOut(row.screenId(), row.name(), row.source(),
                online(row, now), row.lastSeen(), row.configVersion(),
                published ? row.configVersion() : null,
                published && text(row.publishedConfig(), "team_id", "").length() > 0,
                playState(row));
    }

    private ScreenDtos.ScreenConfigOut configView(ScreenRepository.Row row) {
        boolean published = !row.publishedConfig().isEmpty();
        return new ScreenDtos.ScreenConfigOut(row.screenId(), row.configVersion(),
                published ? row.configVersion() : null, row.updatedAt(), playState(row),
                row.config().isEmpty() ? null : toConfig(row.config()));
    }

    private static ScreenDtos.ScreenConfigIn toConfig(Map<String, Object> config) {
        return new ScreenDtos.ScreenConfigIn(text(config, "layout_type", "office"),
                text(config, "theme", "auto"), text(config, "resolution", "1920x1080"),
                text(config, "team_id", null), section(config, "office"),
                section(config, "grid"), section(config, "custom"));
    }

    private void audit(Actor actor, String action, String screenId, Map<String, Object> detail) {
        try {
            jdbc.update("INSERT INTO ops_audit_log (actor_id, action, resource, detail, created_at)"
                            + " VALUES (?, ?, ?, ?, ?)", actor.employeeId(), action,
                    "screen:" + screenId, objectMapper.writeValueAsString(detail),
                    Instant.now().toEpochMilli() / 1000.0);
        } catch (Exception ignored) {
            // 审计失败不影响主流程
        }
    }

    private void ensureAdmin(Actor actor) {
        Authz.ensureAnyAllowed(actor, ADMIN_ACTIONS, Authz.Resource.of("screen"));
    }

    /** 登记结果：明文密钥只在新建时返回一次。 */
    public record Registered(ScreenRepository.Row screen, String secret) {
    }
}
