package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.BuiltinIdentitiesService;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Path;
import java.util.Map;

/**
 * 内置身份端点（P1 二期，D2/D15）— GET/PATCH /api/identities。
 * SoT 与 python 双栈同源（shared seed + store 覆盖）。
 */
@RestController
public class IdentitiesController {

    private final BuiltinIdentitiesService service;

    public IdentitiesController(Environment env) {
        this.service = new BuiltinIdentitiesService(
                io.github.hopewang123456.mailbus.app.SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir")),
                io.github.hopewang123456.mailbus.app.SharedRoots.resolve(env.getProperty("mailbus.root")));
    }

    @GetMapping("/api/identities")
    public Map<String, Object> identities() {
        return service.list();
    }

    @PatchMapping("/api/identities/{id}")
    public Map<String, Object> rename(@PathVariable String id, @RequestBody Map<String, String> body) {
        Map<String, Object> updated = service.rename(id, body.getOrDefault("display_name", ""));
        if (updated == null) {
            return Map.of("status", "error", "error", "not_found",
                    "message", "身份不存在或名称为空: " + id);
        }
        return Map.of("status", "ok", "identity", updated);
    }
}
