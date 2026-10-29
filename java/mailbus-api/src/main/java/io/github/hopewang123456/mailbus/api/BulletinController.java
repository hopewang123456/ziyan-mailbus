package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 公告板（批 A2，2026-10-29）— python {@code handlers_tasks.handle_bulletin}
 * 对等：GET /api/bulletin · GET /api/bulletin/permit ·
 * POST /api/bulletin/post · POST /api/bulletin/permit。
 *
 * <p>存储：store/bulletin.json（公告）+ store/permission.json（bulletin 权限名单）。
 */
@RestController
public class BulletinController {

    private final Path dataDir;

    public BulletinController(Environment env) {
        this.dataDir = io.github.hopewang123456.mailbus.app.SharedRoots
                .resolveDataDir(env.getProperty("mailbus.data-dir"));
    }

    /** GET /api/bulletin — 公告列表（{bulletins: [...]}）。 */
    @GetMapping("/api/bulletin")
    public Map<String, Object> bulletin() {
        Map<String, Object> doc = JsonFiles.readMap(dataDir.resolve("bulletin.json"));
        return doc == null ? Map.of("bulletins", List.of()) : doc;
    }

    /** GET /api/bulletin/permit — 公告权限名单（{permit: [...] | false}）。 */
    @GetMapping("/api/bulletin/permit")
    public Map<String, Object> permitGet() {
        Map<String, Object> perm = JsonFiles.readMap(dataDir.resolve("permission.json"));
        Object bulletin = perm == null ? null : perm.get("bulletin");
        return Map.of("permit", bulletin == null ? Boolean.FALSE : bulletin);
    }

    /** POST /api/bulletin/post — 发布公告（content 必填）。 */
    @PostMapping("/api/bulletin/post")
    public ResponseEntity<Map<String, Object>> post(@RequestBody Map<String, Object> body) {
        String content = str(body.get("content")).trim();
        String author = str(body.get("author")).trim();
        if (content.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "缺少 content"));
        }
        Map<String, Object> doc = JsonFiles.readMap(dataDir.resolve("bulletin.json"));
        if (doc == null) {
            doc = new LinkedHashMap<>();
            doc.put("bulletins", new ArrayList<>());
        }
        List<Object> bulletins = doc.get("bulletins") instanceof List<?> l ? new ArrayList<>(l) : new ArrayList<>();
        String now = nowIso();
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("id", "bulletin-" + now.substring(0, 10) + "-" + (bulletins.size() + 1));
        entry.put("content", content);
        entry.put("author", author.isEmpty() ? "anonymous" : author);
        entry.put("created_at", now);
        bulletins.add(entry);
        doc.put("bulletins", bulletins);
        JsonFiles.write(dataDir.resolve("bulletin.json"), doc);
        return ResponseEntity.ok(Map.of("status", "ok", "entry", entry));
    }

    /** POST /api/bulletin/permit — 配置公告权限（agents 列表，持久化 permission.json）。 */
    @PostMapping("/api/bulletin/permit")
    public ResponseEntity<Map<String, Object>> permitPost(@RequestBody Map<String, Object> body) {
        Object agents = body.get("agents");
        if (!(agents instanceof List<?>)) {
            return ResponseEntity.badRequest().body(Map.of("error", "agents 必须是列表"));
        }
        Map<String, Object> perm = JsonFiles.readMap(dataDir.resolve("permission.json"));
        if (perm == null) {
            perm = new LinkedHashMap<>();
        }
        perm.put("bulletin", agents);
        JsonFiles.write(dataDir.resolve("permission.json"), perm);
        return ResponseEntity.ok(Map.of("status", "ok", "permit", agents));
    }

    /** python clock.now_iso 同格式：本地时区 +08:00，%Y-%m-%dT%H:%M:%S%z（+0800 无冒号）。 */
    /** GET /api/permission — 权限管理读（permission.json；兼容无 permissions 键的旧格式）。 */
    @GetMapping("/api/permission")
    public Map<String, Object> permissionGet() {
        Map<String, Object> data = JsonFiles.readMap(dataDir.resolve("permission.json"));
        if (data == null) {
            return Map.of();
        }
        if (!data.containsKey("permissions")) {
            Map<String, Object> compat = new LinkedHashMap<>(data);
            compat.put("permissions", data);
            compat.put("bulletin", data.get("bulletin") == null ? List.of() : data.get("bulletin"));
            return compat;
        }
        return data;
    }

    /** POST /api/permission — 权限管理写（permissions dict / bulletin list 白名单 + updated_at）。 */
    @PostMapping("/api/permission")
    public ResponseEntity<Map<String, Object>> permissionPost(@RequestBody Map<String, Object> body) {
        Map<String, Object> perm = JsonFiles.readMap(dataDir.resolve("permission.json"));
        if (perm == null) {
            perm = new LinkedHashMap<>();
        }
        if (body.get("permissions") instanceof Map<?, ?> p) {
            perm.put("permissions", p);
        }
        if (body.get("bulletin") instanceof List<?> b) {
            perm.put("bulletin", b);
        }
        perm.put("updated_at", nowIso());
        JsonFiles.write(dataDir.resolve("permission.json"), perm);
        return ResponseEntity.ok(Map.of("status", "ok",
                "permissions", perm.get("permissions") == null ? Map.of() : perm.get("permissions")));
    }

    private static String nowIso() {
        return OffsetDateTime.now(ZoneId.of("Asia/Shanghai"))
                .format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssZ"));
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }
}
