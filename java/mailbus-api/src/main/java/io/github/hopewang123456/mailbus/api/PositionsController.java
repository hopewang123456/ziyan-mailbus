package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.PositionCatalogService;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Path;
import java.util.Map;

/**
 * GET /api/positions — 职位目录（P1 发令窗口起草面板）。
 * Thin REST surface；聚合在 {@link PositionCatalogService}（app 层）。
 */
@RestController
public class PositionsController {

    private final PositionCatalogService catalog;

    public PositionsController(Environment env) {
        this.catalog = new PositionCatalogService(
                io.github.hopewang123456.mailbus.app.SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir")));
    }

    @GetMapping("/api/positions")
    public Map<String, Object> positions() {
        return catalog.catalog();
    }
}
