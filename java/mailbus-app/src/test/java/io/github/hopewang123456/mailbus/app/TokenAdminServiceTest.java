package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * java 机制深化批一（2026-10-30）— Token 生命周期对等
 * （python token_store ensure/resolve/rotate + mailbus_token CIDR/双路径）。
 */
class TokenAdminServiceTest {

    @TempDir
    Path dataDir;

    private TokenAdminService svc;

    @BeforeEach
    void setUp() {
        svc = new TokenAdminService(dataDir);
    }

    @Test
    void ensureGeneratesAndPersists() {
        String t1 = svc.ensureToken();
        assertNotNull(t1);
        assertTrue(t1.length() >= 40); // base64url(32B) ≈ 43 chars
        // 幂等：再次 ensure 同值
        assertEquals(t1, svc.ensureToken());
        // secrets.json 落盘
        assertTrue(Files.isRegularFile(dataDir.resolve("secrets.json")));
        Map<String, Object> sec = JsonFiles.readMap(dataDir.resolve("secrets.json"));
        assertEquals(t1, String.valueOf(sec.get("mailbus_api_token")));
    }

    @Test
    void rotateReplaces() {
        String t1 = svc.ensureToken();
        String t2 = svc.rotateToken();
        assertNotEquals(t1, t2);
        assertEquals(t2, svc.resolveToken());
    }

    @Test
    void maskedViewShape() {
        var out = svc.statusView();
        assertEquals("ok", out.get("status"));
        assertEquals(Boolean.TRUE, out.get("configured"));
        String masked = String.valueOf(out.get("token_masked"));
        assertTrue(masked.contains("…") && masked.length() == 4 + 1 + 4);
    }

    @Test
    void cidrMatching() {
        // 精确 IP
        assertTrue(TokenAdminService.ipInNetwork("127.0.0.1", "127.0.0.1"));
        // v4 前缀
        assertTrue(TokenAdminService.ipInNetwork("192.168.1.50", "192.168.1.0/24"));
        assertFalse(TokenAdminService.ipInNetwork("192.168.2.1", "192.168.1.0/24"));
        // 非整字节前缀 /22
        assertTrue(TokenAdminService.ipInNetwork("10.1.0.5", "10.0.0.0/8"));
        assertTrue(TokenAdminService.ipInNetwork("10.1.2.3", "10.1.0.0/22"));
        assertFalse(TokenAdminService.ipInNetwork("10.1.4.1", "10.1.0.0/22"));
        // v6
        assertTrue(TokenAdminService.ipInNetwork("::1", "::1/128"));
        // 家族不匹配
        assertFalse(TokenAdminService.ipInNetwork("127.0.0.1", "::1/128"));
    }

    @Test
    void writeFreeGateRespectsSwitchAndCidrs() {
        Map<String, Object> cfgOff = Map.of();
        assertFalse(svc.ipMatchesWriteFreeCidrs("127.0.0.1", cfgOff)); // 开关关 → 恒 false

        Map<String, Object> cfgOn = Map.of("auth", Map.of("allow_write_without_token", true));
        assertTrue(svc.ipMatchesWriteFreeCidrs("127.0.0.1", cfgOn)); // 缺省仅 loopback
        assertTrue(svc.ipMatchesWriteFreeCidrs("::1", cfgOn));
        assertFalse(svc.ipMatchesWriteFreeCidrs("192.168.1.9", cfgOn));

        Map<String, Object> cfgWide = Map.of("auth", Map.of(
                "allow_write_without_token", true,
                "write_without_token_cidrs", List.of("192.168.0.0/16")));
        assertTrue(svc.ipMatchesWriteFreeCidrs("192.168.1.9", cfgWide));
        assertFalse(svc.ipMatchesWriteFreeCidrs("10.0.0.1", cfgWide));
    }

    @Test
    void rotateDualPath() {
        String current = svc.ensureToken();
        var ctx = new TokenAdminService.ClientContext("127.0.0.1", "", "");

        // 开关关 + 无 token → 401 unauthorized
        var denied = svc.rotate(ctx, Map.of());
        assertEquals(Boolean.FALSE, denied.get("ok"));
        assertEquals("unauthorized", denied.get("error_code"));

        // 出示正确 token → ok
        var ok = svc.rotate(new TokenAdminService.ClientContext("127.0.0.1", "Bearer " + current, ""), Map.of());
        assertEquals(Boolean.TRUE, ok.get("ok"));
        assertNotEquals(current, ok.get("token"));

        // 白名单开启 → 免旧 token 直接换
        String now = svc.resolveToken();
        var free = svc.rotate(ctx, Map.of("auth", Map.of("allow_write_without_token", true)));
        assertEquals(Boolean.TRUE, free.get("ok"));
        assertNotEquals(now, free.get("token"));

        // 出示旧 token（已失效）→ 拒
        var stale = svc.rotate(new TokenAdminService.ClientContext("8.8.8.8", "Bearer " + current, ""), Map.of());
        assertEquals(Boolean.FALSE, stale.get("ok"));
    }
}
