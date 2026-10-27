package io.github.hopewang123456.mailbus.app;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** P2 收尾 — java RAG 检索（python internal_llm 检索的对等测试；知识库同一目录）。 */
class DocsRagServiceTest {

    private Path rootWithDocs(@TempDir Path tmp) throws IOException {
        Path docs = tmp.resolve("docs/runbooks");
        Files.createDirectories(docs);
        Files.writeString(docs.resolve("guide.md"), """
                # 操作指南
                发令窗口：任意页面右下角「⚡ 发令」按钮。选职位填写表单，或自由需求生成草稿。
                """);
        Files.writeString(docs.resolve("recover.md"), """
                # 恢复手册
                WSL 恢复：先执行 wsl --shutdown，再重启 docker desktop。
                """);
        return tmp;
    }

    @Test
    void retrievesRelevantChunk(@TempDir Path unused) throws IOException {
        Path root = rootWithDocs(Files.createTempDirectory("rag"));
        DocsRagService svc = new DocsRagService(root);
        List<DocsRagService.Citation> hits = svc.retrieve("发令窗口怎么用");
        assertFalse(hits.isEmpty(), "应命中指南");
        assertTrue(hits.get(0).title().contains("guide"));
        assertTrue(hits.get(0).excerpt().contains("发令"));
    }

    @Test
    void noDocsReturnsEmpty(@TempDir Path dataDir) {
        DocsRagService svc = new DocsRagService(dataDir);
        assertTrue(svc.retrieve("任何问题").isEmpty());
    }

    @Test
    void chineseTokenizerExtractsBigrams() {
        List<String> tokens = DocsRagService.tokenize("活跃任务怎么这么多 failed_tasks");
        assertTrue(tokens.contains("活跃"));
        assertTrue(tokens.contains("failed"));
    }
}
