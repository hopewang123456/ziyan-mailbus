package io.github.hopewang123456.mailbus.infra.lock;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * D16 批1：跨进程文件锁。锁名 hash 契约向量由 python
 * {@code tests/test_d16_file_lock.py} 同步生成（改动任一侧即破坏双栈互斥）。
 */
class CrossProcessFileLockTest {

    @TempDir
    Path dataDir;

    /** python 侧 sha256(key)[:16] 实算向量（key 统一正斜杠 + Windows 小写）。 */
    @Test
    void hashContractMatchesPython() {
        // 向量：inbox/a/inbox.json -> bc4e644f629eb63c（python hashlib 实算）
        assertEquals("mailbus-bc4e644f629eb63c.lock",
                CrossProcessFileLock.lockFileFor(dataDir.resolve("inbox").resolve("a").resolve("inbox.json"), dataDir)
                        .getFileName().toString());
        assertEquals("mailbus-95c60ad4a4f84eaf.lock",
                CrossProcessFileLock.lockFileFor(dataDir.resolve("inbox").resolve("ziyan").resolve("inbox.json"), dataDir)
                        .getFileName().toString());
        // dataDir 外目标 → 绝对路径键（正斜杠 + win 小写）；只验证不等于相对键 hash
        Path outside = dataDir.resolveSibling("outside-store").resolve("x.json");
        String outsideName = CrossProcessFileLock.lockFileFor(outside, dataDir).getFileName().toString();
        assertTrue(outsideName.startsWith("mailbus-") && outsideName.endsWith(".lock"));
    }

    /** 锁根默认 dataDir/.locks；env MAILBUS_LOCK_DIR 覆盖。 */
    @Test
    void lockRootDefaultsAndEnvOverride() {
        assertEquals(dataDir.resolve(".locks"), CrossProcessFileLock.lockRoot(dataDir));
    }

    /** 单 JVM 多线程互斥：并发读改写计数必须精确（record lock 同进程不互斥，线程锁先行）。 */
    @Test
    void intraProcessThreadMutex() throws Exception {
        Path target = dataDir.resolve("inbox").resolve("a").resolve("inbox.json");
        writeCount(target, 0);
        int threads = 4;
        int per = 100;
        CountDownLatch start = new CountDownLatch(1);
        List<Thread> ts = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            Thread t = new Thread(() -> {
                try {
                    start.await();
                } catch (InterruptedException ignored) {
                }
                for (int k = 0; k < per; k++) {
                    CrossProcessFileLock.withLock(target, dataDir, () -> {
                        int cur = readCount(target);
                        writeCount(target, cur + 1);
                    });
                }
            });
            t.start();
            ts.add(t);
        }
        start.countDown();
        for (Thread t : ts) {
            t.join(30_000);
        }
        assertEquals(threads * per, readCount(target));
    }

    /** 锁文件常驻（与 python 一致，防跨进程 unlink inode 竞态）。 */
    @Test
    void lockFilePersistentAfterUse() {
        Path target = dataDir.resolve("inbox").resolve("a").resolve("inbox.json");
        writeCount(target, 0);
        Path lock = CrossProcessFileLock.lockFileFor(target, dataDir);
        CrossProcessFileLock.withLock(target, dataDir, () -> {
        });
        assertTrue(Files.exists(lock), "锁文件应在使用后常驻");
    }

    /** 第二个 JVM 进程与本进程并发读改写：OS record lock 跨进程互斥真实验证。 */
    @Test
    void crossProcessJvmMutex() throws Exception {
        Path target = dataDir.resolve("inbox").resolve("a").resolve("inbox.json");
        writeCount(target, 0);
        String cp = System.getProperty("java.class.path");
        Process child = new ProcessBuilder(
                ProcessHandle.current().info().command().orElse("java"),
                "-cp", cp, LockBumpChild.class.getName(),
                target.toString(), dataDir.toString(), "120")
                .inheritIO().start();
        // 本进程同时 bump 60 次（三方对打里去掉 python 那一路的双路版本）
        for (int i = 0; i < 60; i++) {
            CrossProcessFileLock.withLock(target, dataDir, () -> {
                int cur = readCount(target);
                writeCount(target, cur + 1);
            });
        }
        assertEquals(0, child.waitFor());
        assertEquals(180, readCount(target));
    }

    /** 超时抛 IllegalStateException（python TimeoutError 对应）。 */
    @Test
    void timeoutThrows() throws Exception {
        Path target = dataDir.resolve("inbox").resolve("a").resolve("inbox.json");
        writeCount(target, 0);
        Thread holder = new Thread(() ->
                CrossProcessFileLock.withLock(target, dataDir, java.time.Duration.ofSeconds(5), () -> {
                    try {
                        Thread.sleep(1500);
                    } catch (InterruptedException ignored) {
                    }
                    return null;
                }));
        holder.start();
        Thread.sleep(200); // 等 holder 拿到锁
        AtomicInteger hit = new AtomicInteger();
        try {
            CrossProcessFileLock.withLock(target, dataDir, java.time.Duration.ofMillis(300), () -> hit.incrementAndGet());
            throw new AssertionError("应超时");
        } catch (IllegalStateException expected) {
            // 超时路径
        }
        holder.join(10_000);
        assertEquals(0, hit.get());
    }

    // ── helpers：与 JsonFiles 等价的轻量计数文件读写 ──

    private static void writeCount(Path p, int v) {
        try {
            Files.createDirectories(p.getParent());
            Map<String, Object> doc = new LinkedHashMap<>();
            doc.put("a", v);
            Files.writeString(p, "{\"a\": " + v + "}", StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    private static int readCount(Path p) {
        try {
            String s = Files.readString(p, StandardCharsets.UTF_8).replaceAll("[^0-9]", "");
            return s.isEmpty() ? 0 : Integer.parseInt(s);
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    /** 跨进程对打子进程入口（由 crossProcessJvmMutex 启动）。 */
    public static final class LockBumpChild {
        public static void main(String[] args) {
            Path target = Path.of(args[0]);
            Path dataDir = Path.of(args[1]);
            int n = Integer.parseInt(args[2]);
            for (int i = 0; i < n; i++) {
                CrossProcessFileLock.withLock(target, dataDir, () -> {
                    try {
                        int cur = readCount(target);
                        writeCount(target, cur + 1);
                    } catch (RuntimeException e) {
                        System.exit(2);
                    }
                });
            }
        }
    }
}
