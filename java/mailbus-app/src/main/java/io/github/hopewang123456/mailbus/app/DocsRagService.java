package io.github.hopewang123456.mailbus.app;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

/**
 * java 侧轻量 RAG（P2 收尾，D10 对等）— python internal_llm 索引检索的对等实现。
 *
 * <p>知识库：{@code mailbus/docs} 下的全部 Markdown（与 python rag source 同一目录，双栈同一真源）。
 * 检索：关键词计分（问题分词命中次数 × 片段位置），取 top-K 片段——零向量库依赖，
 * 与 python 轻量 chunks 检索同等克制；片断化：按 800 字符切块。
 */
public class DocsRagService {

    private static final int CHUNK_CHARS = 800;
    private static final int TOP_K = 5;

    private final Path docsRoot;

    public DocsRagService(Path mailbusRoot) {
        this.docsRoot = mailbusRoot.resolve("docs");
    }

    public record Citation(String sourceId, String title, String excerpt, int score) {}

    /** 关键词检索 top-K 手册片段；docs 缺失或无命中返回空表。 */
    public List<Citation> retrieve(String question) {
        if (!Files.isDirectory(docsRoot) || question == null || question.isBlank()) {
            return List.of();
        }
        List<String> keywords = tokenize(question);
        if (keywords.isEmpty()) {
            return List.of();
        }
        List<Citation> scored = new ArrayList<>();
        try (Stream<Path> files = Files.walk(docsRoot)) {
            files.filter(p -> p.toString().endsWith(".md")).forEach(p -> {
                String text;
                try {
                    text = Files.readString(p);
                } catch (IOException e) {
                    return;
                }
                String rel = docsRoot.relativize(p).toString().replace('\\', '/');
                for (int i = 0; i < text.length(); i += CHUNK_CHARS) {
                    String chunk = text.substring(i, Math.min(text.length(), i + CHUNK_CHARS));
                    int score = 0;
                    for (String kw : keywords) {
                        int idx = 0;
                        while ((idx = chunk.indexOf(kw, idx)) >= 0) {
                            score += 1;
                            idx += kw.length();
                        }
                    }
                    if (score > 0) {
                        scored.add(new Citation("docs", rel, chunk.length() > 300 ? chunk.substring(0, 300) : chunk, score));
                    }
                }
            });
        } catch (IOException e) {
            return List.of();
        }
        return scored.stream()
                .sorted(Comparator.comparingInt(Citation::score).reversed())
                .limit(TOP_K)
                .toList();
    }

    /** 简易中文分词：提取 2 字以上 CJK 滑窗 + ASCII 词。 */
    static List<String> tokenize(String q) {
        List<String> out = new ArrayList<>();
        StringBuilder ascii = new StringBuilder();
        for (int i = 0; i < q.length(); i++) {
            char c = q.charAt(i);
            if (c >= 0x4e00 && c <= 0x9fff) {
                if (ascii.length() > 0) {
                    addIfUseful(out, ascii.toString());
                    ascii.setLength(0);
                }
                if (i + 1 < q.length() && q.charAt(i + 1) >= 0x4e00 && q.charAt(i + 1) <= 0x9fff) {
                    addIfUseful(out, q.substring(i, i + 2)); // 二元滑窗（轻量，够用）
                }
            } else if (Character.isLetterOrDigit(c)) {
                ascii.append(c);
            } else if (ascii.length() > 0) {
                addIfUseful(out, ascii.toString());
                ascii.setLength(0);
            }
        }
        if (ascii.length() > 0) {
            addIfUseful(out, ascii.toString());
        }
        return out;
    }

    private static void addIfUseful(List<String> out, String s) {
        if (s.length() >= 2 && !out.contains(s)) {
            out.add(s);
        }
    }

    /** 指标上下文（B6 java 侧）：manifest 口径 + calculator 当前真值。 */
    public static String metricsContext(MetricsManifestService manifest, MailbusMetricsCalculator calc) {
        StringBuilder sb = new StringBuilder();
        for (Map<String, Object> m : manifest.metrics()) {
            String id = String.valueOf(m.get("id"));
            Double v = calc.hasSource(id) ? calc.currentValue(id) : null;
            Object zh = m.get("name") instanceof Map<?, ?> nm ? nm.get("zh") : null;
            sb.append("- ").append(zh != null ? zh : id).append("(").append(id).append(") = ")
              .append(v != null ? v : "无源(M1)").append("\n");
        }
        return sb.toString();
    }
}
