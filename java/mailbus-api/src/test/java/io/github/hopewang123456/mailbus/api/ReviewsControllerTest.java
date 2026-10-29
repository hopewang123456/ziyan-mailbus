package io.github.hopewang123456.mailbus.api;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.env.MockEnvironment;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 批 A6 二组（2026-10-29）— reviews 三端点 + repo 名提取 + 501 族。
 */
class ReviewsControllerTest {

    @TempDir
    Path dataDir;

    private ReviewsController controller;

    @BeforeEach
    void setUp() {
        MockEnvironment env = new MockEnvironment();
        env.setProperty("mailbus.data-dir", dataDir.toString());
        controller = new ReviewsController(env);
    }

    @Test
    void extractRepoNameMatrix() {
        assertEquals("mailbus", ReviewsController.extractRepoName("review-mailbus-20260526.md"));
        assertEquals("ziyan-mailbus", ReviewsController.extractRepoName("review-ziyan-mailbus-20261029.md"));
        assertEquals("未知项目（旧报告）", ReviewsController.extractRepoName("review-abc12345-20260526.md"));
        assertEquals("未知项目（旧报告）", ReviewsController.extractRepoName("random.md"));
    }

    @Test
    void reviewsListAndProjects() throws Exception {
        Files.createDirectories(dataDir.resolve("reports"));
        Files.writeString(dataDir.resolve("reports/review-mailbus-20260526.md"), "# 审查 A".repeat(60));
        Files.writeString(dataDir.resolve("reports/review-ziyan-20261029.md"), "# 审查 B");

        var out = controller.reviews();
        assertEquals(2, ((Number) out.get("count")).intValue());
        List<?> reports = (List<?>) out.get("reports");
        // 倒序：ziyan 在前
        assertEquals("review-ziyan-20261029.md", ((java.util.Map<?, ?>) reports.get(0)).get("file"));
        assertEquals("ziyan", ((java.util.Map<?, ?>) reports.get(0)).get("repo"));
        // content 截 300
        assertEquals(300, String.valueOf(((java.util.Map<?, ?>) reports.get(1)).get("content")).length());

        var proj = controller.reviewProjects();
        assertEquals(2, ((Number) proj.get("count")).intValue());
        assertTrue(((java.util.Map<?, ?>) proj.get("projects")).containsKey("mailbus"));
    }

    @Test
    void reviewDetailPreWrapAndSafety() throws Exception {
        Files.createDirectories(dataDir.resolve("reports"));
        Files.writeString(dataDir.resolve("reports/review-x.md"), "# 内容");
        var ok = controller.reviewDetail("review-x.md");
        assertEquals(200, ok.getStatusCode().value());
        String html = String.valueOf(ok.getBody().get("html"));
        assertTrue(html.startsWith("<pre>") && html.endsWith("</pre>"));
        assertEquals("# 内容", ok.getBody().get("raw"));

        assertEquals(404, controller.reviewDetail("../config.json").getStatusCode().value());
        assertEquals(404, controller.reviewDetail("nope.md").getStatusCode().value());
    }

    @Test
    void frameworksAndInstancesFamily() {
        assertEquals(Map_count(controller.frameworks()), 0); // 空骨架
        assertEquals(501, controller.frameworkEnable("f1").getStatusCode().value());
        assertEquals(501, controller.frameworkDisable("f1").getStatusCode().value());
        assertEquals(501, controller.instanceUpsert().getStatusCode().value());
        assertEquals(501, controller.instanceLoadRoles().getStatusCode().value());
        assertEquals(501, controller.instanceDiscover().getStatusCode().value());
        assertEquals(501, controller.instanceTestConnection().getStatusCode().value());
    }

    private static int Map_count(java.util.Map<String, Object> out) {
        return ((java.util.Map<?, ?>) out.get("frameworks")).size();
    }
}
