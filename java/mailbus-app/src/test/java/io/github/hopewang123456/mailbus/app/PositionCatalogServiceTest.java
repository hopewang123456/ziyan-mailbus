package io.github.hopewang123456.mailbus.app;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * P1 职位目录 — python position_catalog 的对等测试（双栈同一 SoT 文件）。
 */
class PositionCatalogServiceTest {

    @Test
    void catalogShapeAndInputsPassthrough(@TempDir Path dataDir) throws IOException {
        Files.createDirectories(dataDir.resolve("roles/json"));
        Files.writeString(dataDir.resolve("roles/json/role-types.json"), """
                {"roles": {
                  "1": {"key": "designer", "display": {"zh": "方案设计师", "en": "Designer"},
                        "candidates": ["agentA"],
                        "inputs": [
                          {"name": "topic", "label": {"zh": "主题"}, "type": "string", "required": true},
                          {"name": "priority", "type": "enum", "options": ["high", "normal"], "default": "normal"}
                        ]},
                  "8": {"key": "developer", "display": {"zh": "开发工程师"}, "candidates": []}
                }}
                """);

        PositionCatalogService svc = new PositionCatalogService(dataDir);
        Map<String, Object> cat = svc.catalog();

        assertEquals("ok", cat.get("status"));
        assertEquals(2, ((Number) cat.get("total")).intValue());
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> positions = (List<Map<String, Object>>) cat.get("positions");

        Map<String, Object> p1 = positions.get(0);
        assertEquals(1, ((Number) p1.get("role_type")).intValue());
        assertEquals("designer", p1.get("key"));
        assertEquals("方案设计师", p1.get("name_zh"));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> inputs = (List<Map<String, Object>>) p1.get("inputs");
        assertEquals(2, inputs.size());
        assertEquals("topic", inputs.get(0).get("name"));
        assertEquals(true, inputs.get(0).get("required"));

        // 无 inputs 的职位缺省空列表（存量 SoT 兼容）
        @SuppressWarnings("unchecked")
        List<Object> empty = (List<Object>) positions.get(1).get("inputs");
        assertTrue(empty.isEmpty());
    }

    @Test
    void missingSoTReturnsEmptyCatalog(@TempDir Path dataDir) {
        PositionCatalogService svc = new PositionCatalogService((Path) dataDir);
        Map<String, Object> cat = svc.catalog();
        assertEquals(0, ((Number) cat.get("total")).intValue());
    }
}
