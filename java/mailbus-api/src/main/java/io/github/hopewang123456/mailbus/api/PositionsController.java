package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.PositionCatalogService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * GET /api/positions — 职位目录（P1 发令窗口起草面板）。
 * Thin REST surface；装配在 boot（M2a 起 resolver 提供负载真值）。
 */
@RestController
public class PositionsController {

    private final PositionCatalogService catalog;

    public PositionsController(PositionCatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/api/positions")
    public Map<String, Object> positions() {
        return catalog.catalog();
    }
}
