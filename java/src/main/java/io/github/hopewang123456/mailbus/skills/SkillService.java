package io.github.hopewang123456.mailbus.skills;

import io.github.hopewang123456.mailbus.agents.AgentRepository;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.events.Outbox;
import io.github.hopewang123456.mailbus.identity.EmployeeRepository;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
public class SkillService {

    private static final Set<String> PATCHABLE = Set.of(
            "name", "source_type", "source_uri", "entry", "note", "enabled");
    private static final Set<String> SOURCE_FIELDS = Set.of(
            "source_type", "source_uri", "entry");
    private static final int MAX_BYTES = 65536;

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final Outbox outbox;
    private final AgentRepository agents;
    private final EmployeeRepository employees;

    public SkillService(JdbcTemplate jdbc, Ids ids, Outbox outbox, AgentRepository agents,
                        EmployeeRepository employees) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.outbox = outbox;
        this.agents = agents;
        this.employees = employees;
    }

    public List<SkillDtos.SkillPackageOut> list() {
        Map<String, List<SkillDtos.SkillBindingOut>> bindings = bindings();
        return jdbc.query("SELECT * FROM skills_packages ORDER BY created_at",
                (row, index) -> mapPackage(row, bindings.getOrDefault(
                        row.getString("package_id"), List.of())));
    }

    @Transactional
    public SkillDtos.SkillPackageOut create(Actor actor, SkillDtos.SkillPackageIn input) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        String name = text(input.name(), "技能包名称", 64);
        String sourceType = sourceType(input.sourceType());
        String sourceUri = sourceUri(input.sourceUri(), sourceType);
        String entry = text(input.entry() == null ? "SKILL.md" : input.entry(), "入口文件", 64);
        String note = note(input.note());
        Instant now = Instant.now();
        String packageId = ids.next("skill");
        jdbc.update("""
                INSERT INTO skills_packages
                    (package_id, name, source_type, source_uri, entry, version, enabled, note,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, '', 1, ?, ?, ?)
                """, packageId, name, sourceType, sourceUri, entry, note,
                now.getEpochSecond(), now.getEpochSecond());
        outbox.enqueue("skills.package_created", Map.of("package_id", packageId, "name", name));
        return load(packageId).withBindings(List.of());
    }

    @Transactional
    public SkillDtos.SkillPackageOut update(Actor actor, String packageId,
                                            Map<String, Object> changes) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        SkillDtos.SkillPackageOut current = load(packageId);
        for (String key : changes.keySet()) {
            if (!PATCHABLE.contains(key)) {
                throw ApiException.conflict("invalid_state", "不允许修改字段：" + key);
            }
        }
        boolean sourceChanged = changes.keySet().stream().anyMatch(SOURCE_FIELDS::contains);
        String sourceType = changes.containsKey("source_type")
                ? sourceType(String.valueOf(changes.get("source_type"))) : current.sourceType();
        String name = changes.containsKey("name")
                ? text(String.valueOf(changes.get("name")), "技能包名称", 64) : current.name();
        String sourceUri = changes.containsKey("source_uri")
                ? sourceUri(String.valueOf(changes.get("source_uri")), sourceType)
                : current.sourceUri();
        String entry = changes.containsKey("entry")
                ? text(String.valueOf(changes.get("entry")), "入口文件", 64) : current.entry();
        String note = changes.containsKey("note")
                ? note(String.valueOf(changes.get("note"))) : current.note();
        boolean enabled = changes.containsKey("enabled")
                ? Boolean.parseBoolean(String.valueOf(changes.get("enabled"))) : current.enabled();
        String version = sourceChanged ? "" : current.version();
        String lastError = sourceChanged ? null : current.lastError();
        Instant lastChecked = sourceChanged ? null : current.lastCheckedAt();
        Instant now = Instant.now();
        jdbc.update("""
                UPDATE skills_packages SET name = ?, source_type = ?, source_uri = ?, entry = ?,
                    version = ?, enabled = ?, note = ?, last_error = ?, last_checked_at = ?,
                    updated_at = ? WHERE package_id = ?
                """, name, sourceType, sourceUri, entry, version, enabled ? 1 : 0, note,
                lastError, lastChecked == null ? null : lastChecked.getEpochSecond(),
                now.getEpochSecond(), packageId);
        outbox.enqueue("skills.package_updated", Map.of("package_id", packageId));
        return load(packageId);
    }

    @Transactional
    public SkillDtos.SkillPackageOut refresh(Actor actor, String packageId) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        SkillDtos.SkillPackageOut current = load(packageId);
        Probe probe = probe(current.sourceType(), current.sourceUri(), current.entry());
        Instant now = Instant.now();
        String version = probe.reachable()
                ? (probe.version() == null || probe.version().isBlank()
                ? current.version() : probe.version())
                : current.version();
        String error = probe.reachable() ? null : probe.error();
        jdbc.update("""
                UPDATE skills_packages SET version = ?, last_error = ?, last_checked_at = ?,
                    updated_at = ? WHERE package_id = ?
                """, version, error, now.getEpochSecond(), now.getEpochSecond(), packageId);
        outbox.enqueue(probe.reachable() ? "skills.refresh_succeeded"
                : "skills.refresh_failed", Map.of("package_id", packageId));
        return load(packageId);
    }

    @Transactional
    public void delete(Actor actor, String packageId) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        load(packageId);
        jdbc.update("DELETE FROM skills_bindings WHERE package_id = ?", packageId);
        jdbc.update("DELETE FROM skills_packages WHERE package_id = ?", packageId);
        outbox.enqueue("skills.package_deleted", Map.of("package_id", packageId));
    }

    @Transactional
    public SkillDtos.SkillPackageOut bind(Actor actor, String packageId,
                                          SkillDtos.SkillBindingIn input) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        load(packageId);
        String targetType = input.targetType();
        if (!"agent".equals(targetType) && !"employee".equals(targetType)) {
            throw ApiException.conflict("invalid_state", "绑定目标只支持 agent 或 employee");
        }
        if ("agent".equals(targetType) && agents.find(input.targetId()).isEmpty()) {
            throw ApiException.notFound("Agent 不存在");
        }
        if ("employee".equals(targetType) && employees.find(input.targetId()).isEmpty()) {
            throw ApiException.notFound("员工不存在");
        }
        boolean enabled = input.enabled() == null || input.enabled();
        jdbc.update("""
                INSERT INTO skills_bindings
                    (package_id, target_type, target_id, enabled, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (package_id, target_type, target_id) DO UPDATE SET
                    enabled = excluded.enabled
                """, packageId, targetType, input.targetId(), enabled ? 1 : 0,
                Instant.now().getEpochSecond());
        outbox.enqueue("skills.binding_changed", Map.of("package_id", packageId,
                "target_type", targetType, "target_id", input.targetId()));
        return load(packageId);
    }

    public List<SkillDtos.EffectiveSkillOut> effective(String targetType, String targetId) {
        String agentId;
        List<Binding> own;
        if ("agent".equals(targetType)) {
            if (agents.find(targetId).isEmpty()) {
                throw ApiException.notFound("Agent 不存在");
            }
            agentId = targetId;
            own = List.of();
        } else if ("employee".equals(targetType)) {
            var employee = employees.find(targetId)
                    .orElseThrow(() -> ApiException.notFound("员工不存在"));
            agentId = employee.agentId();
            own = bindingsOf("employee", targetId);
        } else {
            throw ApiException.badRequest("target_type 只支持 agent 或 employee");
        }
        Map<String, Binding> merged = new LinkedHashMap<>();
        if (agentId != null) {
            bindingsOf("agent", agentId).forEach(binding -> merged.put(binding.packageId(), binding));
        }
        own.forEach(binding -> merged.put(binding.packageId(), binding));
        Map<String, SkillDtos.SkillPackageOut> packages = new LinkedHashMap<>();
        for (SkillDtos.SkillPackageOut item : list()) {
            packages.put(item.packageId(), item);
        }
        List<SkillDtos.EffectiveSkillOut> result = new ArrayList<>();
        for (Binding binding : merged.values()) {
            SkillDtos.SkillPackageOut pkg = packages.get(binding.packageId());
            if (pkg == null) {
                continue;
            }
            String origin = binding.targetType();
            result.add(new SkillDtos.EffectiveSkillOut(pkg.packageId(), pkg.name(),
                    pkg.sourceType(), pkg.sourceUri(), pkg.entry(), pkg.version(),
                    pkg.enabled() && binding.enabled(), pkg.note(), origin));
        }
        result.sort(Comparator.comparing(SkillDtos.EffectiveSkillOut::name));
        return result;
    }

    private SkillDtos.SkillPackageOut load(String packageId) {
        List<SkillDtos.SkillPackageOut> rows = jdbc.query(
                "SELECT * FROM skills_packages WHERE package_id = ?",
                (row, index) -> mapPackage(row, List.of()), packageId);
        SkillDtos.SkillPackageOut pkg = rows.stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("技能包不存在"));
        return pkg.withBindings(bindings().getOrDefault(packageId, List.of()));
    }

    private Map<String, List<SkillDtos.SkillBindingOut>> bindings() {
        Map<String, List<SkillDtos.SkillBindingOut>> map = new LinkedHashMap<>();
        jdbc.query("SELECT * FROM skills_bindings ORDER BY created_at", row -> {
            map.computeIfAbsent(row.getString("package_id"), key -> new ArrayList<>())
                    .add(new SkillDtos.SkillBindingOut(row.getString("target_type"),
                            row.getString("target_id"), row.getInt("enabled") == 1));
        });
        return map;
    }

    private List<Binding> bindingsOf(String targetType, String targetId) {
        return jdbc.query("""
                SELECT * FROM skills_bindings WHERE target_type = ? AND target_id = ?
                """, (row, index) -> new Binding(row.getString("package_id"),
                row.getString("target_type"), row.getString("target_id"),
                row.getInt("enabled") == 1), targetType, targetId);
    }

    private SkillDtos.SkillPackageOut mapPackage(java.sql.ResultSet row,
                                                 List<SkillDtos.SkillBindingOut> bindings)
            throws java.sql.SQLException {
        return new SkillDtos.SkillPackageOut(
                row.getString("package_id"), row.getString("name"), row.getString("source_type"),
                row.getString("source_uri"), row.getString("entry"), row.getString("version"),
                row.getInt("enabled") == 1, row.getString("note"),
                nullableInstant(row, "last_checked_at"), row.getString("last_error"),
                Instant.ofEpochSecond((long) row.getDouble("created_at")),
                Instant.ofEpochSecond((long) row.getDouble("updated_at")), bindings);
    }

    private Instant nullableInstant(java.sql.ResultSet row, String column)
            throws java.sql.SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : Instant.ofEpochSecond((long) value);
    }

    private Probe probe(String sourceType, String sourceUri, String entry) {
        try {
            if ("local".equals(sourceType)) {
                Path path = Path.of(sourceUri);
                if (!Files.exists(path)) {
                    return Probe.failed("来源路径不存在");
                }
                Path target = Files.isDirectory(path) ? path.resolve(entry) : path;
                if (!Files.isRegularFile(target)) {
                    return Probe.failed("入口文件不存在：" + entry);
                }
                String text = readLimited(Files.newInputStream(target));
                return Probe.ok(versionOf(text));
            }
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5)).build();
            HttpRequest request = HttpRequest.newBuilder(URI.create(sourceUri))
                    .timeout(Duration.ofSeconds(5))
                    .header("User-Agent", "mailbus-skill-probe").GET().build();
            HttpResponse<InputStream> response = client.send(request,
                    HttpResponse.BodyHandlers.ofInputStream());
            if (response.statusCode() >= 400) {
                return Probe.failed("HTTP " + response.statusCode());
            }
            return Probe.ok(versionOf(readLimited(response.body())));
        } catch (Exception exception) {
            String message = exception.getMessage() == null
                    ? exception.getClass().getSimpleName() : exception.getMessage();
            return Probe.failed(message.length() > 200 ? message.substring(0, 200) : message);
        }
    }

    private String readLimited(InputStream stream) throws Exception {
        try (stream) {
            byte[] bytes = stream.readNBytes(MAX_BYTES);
            return new String(bytes, StandardCharsets.UTF_8);
        }
    }

    private String versionOf(String text) {
        int count = 0;
        for (String line : text.split("\\R")) {
            if (count++ >= 40) {
                break;
            }
            int index = line.indexOf(':');
            if (index < 0) {
                continue;
            }
            String key = line.substring(0, index).strip().toLowerCase();
            if ("version".equals(key) || "skill_version".equals(key)) {
                return line.substring(index + 1).strip().replace("\"", "").replace("'", "");
            }
        }
        return "";
    }

    private String sourceType(String value) {
        if (!"local".equals(value) && !"http".equals(value)) {
            throw ApiException.domain("skill_source_invalid", "来源类型只支持 local 或 http");
        }
        return value;
    }

    private String sourceUri(String value, String sourceType) {
        String uri = text(value, "来源地址", 512);
        if ("http".equals(sourceType) && !uri.startsWith("http://") && !uri.startsWith("https://")) {
            throw ApiException.domain("skill_source_invalid", "http 来源必须是 http(s) 地址");
        }
        return uri;
    }

    private String text(String value, String label, int limit) {
        String text = value == null ? "" : value.strip();
        if (text.isEmpty()) {
            throw ApiException.conflict("invalid_state", label + "不能为空");
        }
        if (text.length() > limit) {
            throw ApiException.conflict("invalid_state", label + "不能超过 " + limit + " 个字符");
        }
        return text;
    }

    private String note(String value) {
        return value == null ? "" : value.strip();
    }

    private record Probe(boolean reachable, String version, String error) {
        static Probe ok(String version) {
            return new Probe(true, version, null);
        }

        static Probe failed(String error) {
            return new Probe(false, "", error);
        }
    }

    private record Binding(String packageId, String targetType, String targetId, boolean enabled) {
    }
}
