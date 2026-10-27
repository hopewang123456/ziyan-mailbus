package io.github.hopewang123456.mailbus.app;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

/** P1 二期 — 内置身份注册表对等测试（双栈同一 SoT：seed + store 覆盖）。 */
class BuiltinIdentitiesServiceTest {

    private Path seedRoot(@TempDir Path tmp) throws IOException {
        Path seed = tmp.resolve("config/mailbus");
        Files.createDirectories(seed);
        Files.writeString(seed.resolve("builtin-identities.json"), """
                {"identities": [
                  {"id": "ziyan", "display_name": "子言", "role": "owner", "builtin": true}
                ]}
                """);
        return tmp;
    }

    @Test
    @SuppressWarnings("unchecked")
    void listFromSeedAndRenamePersistsOverride(@TempDir Path dataDir) throws IOException {
        Path root = seedRoot(Files.createTempDirectory("seed"));
        BuiltinIdentitiesService svc = new BuiltinIdentitiesService(dataDir, root);

        Map<String, Object> list = svc.list();
        assertEquals("ok", list.get("status"));
        List<Map<String, Object>> identities = (List<Map<String, Object>>) list.get("identities");
        assertEquals(1, identities.size());
        assertEquals("ziyan", identities.get(0).get("id"));
        assertEquals("子言", identities.get(0).get("display_name"));

        Map<String, Object> updated = svc.rename("ziyan", "老板");
        assertNotNull(updated);
        assertEquals("老板", updated.get("display_name"));
        assertEquals("owner", updated.get("role")); // id/role 稳定

        // 覆盖持久化：新实例重读
        BuiltinIdentitiesService svc2 = new BuiltinIdentitiesService(dataDir, root);
        assertEquals("老板", ((List<Map<String, Object>>) svc2.list().get("identities")).get(0).get("display_name"));
    }

    @Test
    void renameRejectsUnknownAndBlank(@TempDir Path dataDir) throws IOException {
        Path root = seedRoot(Files.createTempDirectory("seed"));
        BuiltinIdentitiesService svc = new BuiltinIdentitiesService(dataDir, root);
        assertNull(svc.rename("ghost", "名"));
        assertNull(svc.rename("ziyan", "   "));
    }
}
