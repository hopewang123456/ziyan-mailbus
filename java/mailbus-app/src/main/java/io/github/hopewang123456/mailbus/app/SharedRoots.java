package io.github.hopewang123456.mailbus.app;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * shared/ 根与 store 数据目录解析（P2/P3）——兼容 serve 的不同工作目录。
 * 显式属性值最优先；探测命中（shared 探测 config/mailbus，store 探测目录存在）为准。
 * 保持零 Spring 依赖（app 层纪律），属性值由调用方传入。
 */
public final class SharedRoots {

    private SharedRoots() {
    }

    public static Path resolve(String rootProperty) {
        if (rootProperty != null && !rootProperty.isBlank()) {
            return Path.of(rootProperty);
        }
        for (String cand : List.of("../shared", "../../shared", "../../../shared", "shared")) {
            Path p = Path.of(cand);
            if (Files.isDirectory(p.resolve("config/mailbus"))) {
                return p.toAbsolutePath().normalize();
            }
        }
        return Path.of("../shared");
    }

    /** data 目录（store）解析：显式属性优先且存在；否则探测常用相对位。 */
    public static Path resolveDataDir(String dataDirProperty) {
        if (dataDirProperty != null && !dataDirProperty.isBlank()) {
            Path p = Path.of(dataDirProperty);
            if (Files.isDirectory(p)) {
                return p;
            }
        }
        for (String cand : List.of("../shared/store", "../../shared/store", "shared/store", "store")) {
            Path p = Path.of(cand);
            if (Files.isDirectory(p)) {
                return p.toAbsolutePath().normalize();
            }
        }
        return Path.of(dataDirProperty == null || dataDirProperty.isBlank() ? "./store" : dataDirProperty);
    }
}
