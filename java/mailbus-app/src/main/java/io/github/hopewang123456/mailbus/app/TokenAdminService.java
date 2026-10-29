package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.nio.file.Path;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Mailbus API Token 生命周期（java 机制深化批一，2026-10-30）— python
 * {@code application/mailbus_token.py} + {@code adapters/config/token_store.py} 对等：
 * secrets.json 持久化（MAILBUS_API_TOKEN env 优先）、ensure/resolve/rotate、
 * 无 Token 写白名单 CIDR 匹配、rotate 双路径（白名单免旧 token / 其余须出示）。
 */
public class TokenAdminService {

    private static final String SECRETS_NAME = "secrets.json";
    private static final String TOKEN_KEY = "mailbus_api_token";
    private static final List<String> DEFAULT_WRITE_FREE_CIDRS = List.of("127.0.0.1/32", "::1/128");

    private final Path dataDir;
    private final SecureRandom random = new SecureRandom();

    public TokenAdminService(Path dataDir) {
        this.dataDir = dataDir;
    }

    /** 请求方上下文（python ClientContext）。 */
    public record ClientContext(String remoteAddr, String authorization, String apiKeyHeader) {
        public String presentedToken() {
            String auth = authorization == null ? "" : authorization.trim();
            if (auth.toLowerCase().startsWith("bearer ")) {
                return auth.substring(7).trim();
            }
            return apiKeyHeader == null ? "" : apiKeyHeader.trim();
        }
    }

    // ── token store ──

    private Path secretsPath() {
        return dataDir.resolve(SECRETS_NAME);
    }

    private Map<String, Object> readSecrets() {
        Map<String, Object> m = JsonFiles.readMap(secretsPath());
        return m == null ? new LinkedHashMap<>() : m;
    }

    /** python resolve_token：env > secrets.json。 */
    public String resolveToken() {
        String env = System.getenv("MAILBUS_API_TOKEN");
        if (env != null && !env.isBlank()) {
            return env.trim();
        }
        String tok = str(readSecrets().get(TOKEN_KEY));
        return tok.isEmpty() ? null : tok;
    }

    /** python ensure_token：无则生成（token_urlsafe(32) 等价 base64url 32 字节）。 */
    public String ensureToken() {
        String existing = resolveToken();
        if (existing != null) {
            return existing;
        }
        synchronized (this) {
            String again = str(readSecrets().get(TOKEN_KEY));
            if (!again.isEmpty()) {
                return again;
            }
            String token = newToken();
            Map<String, Object> data = readSecrets();
            data.put(TOKEN_KEY, token);
            JsonFiles.write(secretsPath(), data);
            return token;
        }
    }

    /** python rotate_token：无条件换新。 */
    public String rotateToken() {
        synchronized (this) {
            String token = newToken();
            Map<String, Object> data = readSecrets();
            data.put(TOKEN_KEY, token);
            JsonFiles.write(secretsPath(), data);
            return token;
        }
    }

    private String newToken() {
        byte[] buf = new byte[32];
        random.nextBytes(buf);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(buf);
    }

    // ── 鉴权语义（python authorize_write / rotate 双路径）──

    private Map<String, Object> authBlock(Map<String, Object> config) {
        Object auth = config == null ? null : config.get("auth");
        return auth instanceof Map<?, ?> m ? cast(m) : Map.of();
    }

    private List<String> writeFreeCidrs(Map<String, Object> config) {
        Map<String, Object> auth = authBlock(config);
        Object raw = auth.get("write_without_token_cidrs");
        if (!(raw instanceof List<?> l) || l.isEmpty()) {
            raw = auth.get("exempt_cidrs");
        }
        if (!(raw instanceof List<?> l2) || l2.isEmpty()) {
            return List.of();
        }
        return l2.stream().map(String::valueOf).filter(s -> !s.isBlank()).toList();
    }

    public boolean allowWriteWithoutTokenEnabled(Map<String, Object> config) {
        return Boolean.TRUE.equals(authBlock(config).get("allow_write_without_token"));
    }

    /** python ip_matches_write_free_cidrs：开关开启 + IP 落白名单（缺省仅 loopback）。 */
    public boolean ipMatchesWriteFreeCidrs(String addr, Map<String, Object> config) {
        if (!allowWriteWithoutTokenEnabled(config)) {
            return false;
        }
        String a = normalizeAddr(addr);
        if (a.isEmpty()) {
            return false;
        }
        List<String> cidrs = writeFreeCidrs(config);
        if (cidrs.isEmpty()) {
            cidrs = DEFAULT_WRITE_FREE_CIDRS;
        }
        for (String cidr : cidrs) {
            if (cidr.equals(a) || ipInNetwork(a, cidr)) {
                return true;
            }
        }
        return false;
    }

    private static String normalizeAddr(String addr) {
        String a = addr == null ? "" : addr.trim().toLowerCase();
        if (a.startsWith("::ffff:")) {
            a = a.substring(7);
        }
        if (a.equals("localhost")) {
            a = "127.0.0.1";
        }
        return a.split("%", 2)[0];
    }

    /** 单 IP 或 CIDR 匹配（无第三方依赖的手写 CIDR v4/v6 前缀比较）。 */
    static boolean ipInNetwork(String addr, String cidr) {
        try {
            String[] parts = cidr.split("/");
            byte[] net = java.net.InetAddress.getByName(parts[0]).getAddress();
            int prefix = parts.length > 1 ? Integer.parseInt(parts[1]) : net.length * 8;
            byte[] ip = java.net.InetAddress.getByName(addr).getAddress();
            if (ip.length != net.length) {
                return false; // v4 vs v6 家族不匹配
            }
            int fullBytes = prefix / 8;
            int remBits = prefix % 8;
            for (int i = 0; i < fullBytes; i++) {
                if (ip[i] != net[i]) {
                    return false;
                }
            }
            if (remBits > 0 && fullBytes < net.length) {
                int mask = 0xFF << (8 - remBits);
                if ((ip[fullBytes] & mask) != (net[fullBytes] & mask)) {
                    return false;
                }
            }
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /** python rotate_token 双路径。 */
    public Map<String, Object> rotate(ClientContext ctx, Map<String, Object> config) {
        if (ipMatchesWriteFreeCidrs(ctx.remoteAddr(), config)) {
            return Map.of("ok", true, "token", rotateToken(), "message", "rotated");
        }
        String expected = resolveToken();
        String presented = ctx.presentedToken();
        if (expected == null || presented.isEmpty() || !presented.equals(expected)) {
            return Map.of("ok", false, "error", "unauthorized", "error_code", "unauthorized");
        }
        return Map.of("ok", true, "token", rotateToken(), "message", "rotated");
    }

    /** masked 视图（python handle_mailbus_token GET 形状）。 */
    public Map<String, Object> statusView() {
        String tok = ensureToken();
        String masked = tok.length() > 8 ? tok.substring(0, 4) + "…" + tok.substring(tok.length() - 4) : "***";
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("configured", resolveToken() != null);
        out.put("token_masked", masked);
        out.put("hint", "写操作使用 Authorization: Bearer <token>。默认本机也需要 Token；可在配置合页填写或开启 allow_write_without_token。");
        return out;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o).trim();
    }
}
