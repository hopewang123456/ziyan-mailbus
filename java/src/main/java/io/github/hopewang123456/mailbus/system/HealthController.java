package io.github.hopewang123456.mailbus.system;

import io.github.hopewang123456.mailbus.db.MigrationRunner;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
public class HealthController {

    private final MigrationRunner migrationRunner;

    public HealthController(MigrationRunner migrationRunner) {
        this.migrationRunner = migrationRunner;
    }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", "ok");
        body.put("service", "mailbus");
        body.put("version", "0.2.0");
        body.put("schema_version", migrationRunner.schemaVersion());
        body.put("time", Instant.now().toString());
        return body;
    }
}
