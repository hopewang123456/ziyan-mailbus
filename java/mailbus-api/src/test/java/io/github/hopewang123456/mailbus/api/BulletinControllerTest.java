package io.github.hopewang123456.mailbus.api;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.env.MockEnvironment;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 批 A2（2026-10-29）— 公告板四端点双栈形状对等
 * （python handlers_tasks.handle_bulletin / handle_bulletin_post /
 * handle_bulletin_permit / handle_bulletin_permit_get）。
 */
class BulletinControllerTest {

    @TempDir
    Path dataDir;

    private BulletinController controller;

    @BeforeEach
    void setUp() throws Exception {
        Files.createDirectories(dataDir);
        MockEnvironment env = new MockEnvironment();
        env.setProperty("mailbus.data-dir", dataDir.toString());
        controller = new BulletinController(env);
    }

    @Test
    void bulletinEmptyDefault() {
        Map<String, Object> out = controller.bulletin();
        assertEquals(List.of(), out.get("bulletins"));
    }

    @Test
    void postRequiresContent() {
        var resp = controller.post(Map.of("author", "z"));
        assertEquals(400, resp.getStatusCode().value());
        assertEquals("缺少 content", resp.getBody().get("error"));
    }

    @Test
    void postAppendsAndPersists() {
        var resp = controller.post(Map.of("content", "今天发布 v2", "author", "子言"));
        assertEquals(200, resp.getStatusCode().value());
        @SuppressWarnings("unchecked")
        Map<String, Object> entry = (Map<String, Object>) resp.getBody().get("entry");
        assertEquals("今天发布 v2", entry.get("content"));
        assertEquals("子言", entry.get("author"));
        assertTrue(String.valueOf(entry.get("id")).startsWith("bulletin-"));
        assertTrue(String.valueOf(entry.get("created_at")).matches("\\d{4}-\\d{2}-\\d{2}T.*[+-]\\d{4}"));

        // 落盘 + 再读回
        Map<String, Object> reread = controller.bulletin();
        List<?> items = (List<?>) reread.get("bulletins");
        assertEquals(1, items.size());
        assertEquals("今天发布 v2", ((Map<?, ?>) items.get(0)).get("content"));
    }

    @Test
    void permitRoundTrip() {
        var bad = controller.permitPost(Map.of("agents", "not-a-list"));
        assertEquals(400, bad.getStatusCode().value());
        assertEquals("agents 必须是列表", bad.getBody().get("error"));

        var ok = controller.permitPost(Map.of("agents", List.of("agentA", "agentB")));
        assertEquals(200, ok.getStatusCode().value());
        assertEquals(List.of("agentA", "agentB"), ok.getBody().get("permit"));

        Map<String, Object> read = controller.permitGet();
        assertEquals(List.of("agentA", "agentB"), read.get("permit"));
    }

    @Test
    void permitGetDefaultFalse() {
        assertEquals(Boolean.FALSE, controller.permitGet().get("permit"));
    }
}
