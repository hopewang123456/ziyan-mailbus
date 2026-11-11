package io.github.hopewang123456.mailbus.infra.lock;

import java.io.IOException;
import java.io.RandomAccessFile;
import java.io.UncheckedIOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Supplier;

/**
 * 跨进程文件锁 — python {@code lib/infra/utils.py file_lock} 的 java 对应物（D16 批1，
 * 消息存储 SoT 统一地基）。双栈对同一目标文件必须命中<b>同一个锁文件、同一字节区域</b>：
 *
 * <ul>
 *   <li>锁文件名：{@code mailbus-<sha256(key)[:16]>.lock}，key 规则与 python
 *       {@code _store_relative_key} 逐字节一致 —— dataDir 内目标用相对路径
 *       （容器内挂载路径不同仍命中），dataDir 外退回绝对路径；统一正斜杠；
 *       Windows 统一小写。</li>
 *   <li>OS 锁：FileChannel exclusive region [0,1)（win: LockFileEx / unix: fcntl
 *       record lock），与 python msvcrt.locking / fcntl.lockf 对称互斥。</li>
 *   <li>双层互斥：进程内 per-target {@link ReentrantLock} 先行（POSIX record lock
 *       同进程内不互斥，且同 JVM 重叠 region 会 OverlappingFileLockException）。</li>
 *   <li>锁文件常驻不删（跨进程 unlink 有 inode 竞态，与 python 侧一致）。</li>
 * </ul>
 *
 * <p>锁根解析与 python 相同：env {@code MAILBUS_LOCK_DIR} &gt; {@code <dataDir>/.locks}。
 */
public final class CrossProcessFileLock {

    /** 与 python file_lock 默认超时一致（10s），超时抛 IllegalStateException。 */
    private static final Duration DEFAULT_TIMEOUT = Duration.ofSeconds(10);

    private static final ConcurrentHashMap<String, ReentrantLock> INTRA = new ConcurrentHashMap<>();

    private CrossProcessFileLock() {
    }

    /** 锁根：env MAILBUS_LOCK_DIR &gt; dataDir/.locks（与 python _resolve_lock_root 一致）。 */
    public static Path lockRoot(Path dataDir) {
        String env = System.getenv("MAILBUS_LOCK_DIR");
        if (env != null && !env.isBlank()) {
            return Paths.get(env.trim());
        }
        return dataDir.resolve(".locks");
    }

    /** 目标文件 → 锁文件（跨栈 hash 契约，见类注释）。 */
    public static Path lockFileFor(Path target, Path dataDir) {
        String key = relativeKey(target, dataDir);
        byte[] digest = sha256(key);
        String hex = HexFormat.of().formatHex(digest).substring(0, 16);
        return lockRoot(dataDir).resolve("mailbus-" + hex + ".lock");
    }

    /** 在跨进程锁内执行（带默认超时）。 */
    public static void withLock(Path target, Path dataDir, Runnable body) {
        withLock(target, dataDir, DEFAULT_TIMEOUT, () -> {
            body.run();
            return null;
        });
    }

    /** 在跨进程锁内执行并取回结果（带默认超时）。 */
    public static <T> T withLock(Path target, Path dataDir, Supplier<T> body) {
        return withLock(target, dataDir, DEFAULT_TIMEOUT, body);
    }

    /** 在跨进程锁内执行并取回结果；获取失败抛 IllegalStateException（python TimeoutError 对应）。 */
    public static <T> T withLock(Path target, Path dataDir, Duration timeout, Supplier<T> body) {
        Path lockFile = lockFileFor(target, dataDir);
        ReentrantLock intra = INTRA.computeIfAbsent(lockFile.toString(), k -> new ReentrantLock());
        try {
            Files.createDirectories(lockFile.getParent());
        } catch (IOException e) {
            throw new UncheckedIOException("cannot create lock dir " + lockFile.getParent(), e);
        }
        boolean intraAcquired = false;
        try {
            intraAcquired = intra.tryLock(timeout.toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("lock wait interrupted (target=" + target + ")", e);
        }
        if (!intraAcquired) {
            throw new IllegalStateException("无法获取进程内文件锁 (target=" + target + ", timeout=" + timeout.toSeconds() + "s)");
        }
        try (RandomAccessFile raf = new RandomAccessFile(lockFile.toFile(), "rw");
             FileChannel ch = raf.getChannel()) {
            long deadline = System.nanoTime() + timeout.toNanos();
            FileLock osLock = null;
            while (osLock == null) {
                try {
                    // region [0,1) exclusive —— 与 python msvcrt.locking / fcntl.lockf 同字节区
                    osLock = ch.tryLock(0, 1, false);
                } catch (IOException | IllegalStateException e) {
                    osLock = null;
                }
                if (osLock == null) {
                    if (System.nanoTime() >= deadline) {
                        throw new IllegalStateException("无法获取文件锁 (target=" + target + ", timeout=" + timeout.toSeconds() + "s)");
                    }
                    Thread.sleep(100);
                }
            }
            try {
                return body.get();
            } finally {
                try {
                    osLock.release();
                } catch (IOException ignored) {
                    // 释放失败随 fd 关闭兜底
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("lock wait interrupted (target=" + target + ")", e);
        } catch (IOException e) {
            throw new UncheckedIOException("cannot lock " + lockFile, e);
        } finally {
            intra.unlock();
        }
    }

    /** 与 python _store_relative_key 逐字节一致：dataDir 内相对、外绝对；正斜杠；win 小写。 */
    static String relativeKey(Path target, Path dataDir) {
        Path norm = target.toAbsolutePath().normalize();
        Path base = dataDir.toAbsolutePath().normalize();
        String key;
        if (norm.startsWith(base)) {
            key = base.relativize(norm).toString();
        } else {
            key = norm.toString();
        }
        key = key.replace('\\', '/');
        if (System.getProperty("os.name", "").toLowerCase().contains("win")) {
            key = key.toLowerCase();
        }
        return key;
    }

    private static byte[] sha256(String s) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(s.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
