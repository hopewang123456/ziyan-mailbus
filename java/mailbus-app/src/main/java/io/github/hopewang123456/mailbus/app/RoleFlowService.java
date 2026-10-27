package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.nio.file.Path;
import java.util.Map;

/**
 * 角色流转规则 — python {@code orchestration/role_flow.py} 的 SoT 部分
 * 对等（M2b）：读 {dataDir}/roles/json/role-flow.json
 * （{transitions, terminal, blocked_fallback_role_type}）。legacy 中文
 * _FLOW_RULES 硬编码 shim 不对等（java 无历史包袱，D9）。
 */
public class RoleFlowService {

    private final Path flowPath;

    public RoleFlowService(Path dataDir) {
        this.flowPath = dataDir.resolve("roles/json/role-flow.json");
    }

    private Map<String, Object> flow() {
        Map<String, Object> doc = JsonFiles.readMap(flowPath);
        return doc == null ? Map.of() : doc;
    }

    /** transition 命中 → to_role_type；未命中返回 null。 */
    public Integer nextRoleType(int roleType, String conclusion) {
        String c = str(conclusion).toLowerCase();
        Object transitions = flow().get("transitions");
        if (transitions instanceof java.util.List<?> list) {
            for (Object o : list) {
                if (!(o instanceof Map<?, ?> t)) {
                    continue;
                }
                if (intOr(t.get("from_role_type"), -1) == roleType
                        && str(t.get("conclusion")).toLowerCase().equals(c)) {
                    Object to = t.get("to_role_type");
                    return to == null ? null : intOr(to, -1);
                }
            }
        }
        return null;
    }

    /** terminal 规则命中（role_type+conclusion）→ 链终态。 */
    public boolean isTerminal(int roleType, String conclusion) {
        String c = str(conclusion).toLowerCase();
        Object terminal = flow().get("terminal");
        if (terminal instanceof java.util.List<?> list) {
            for (Object o : list) {
                if (!(o instanceof Map<?, ?> t)) {
                    continue;
                }
                if (intOr(t.get("role_type"), -1) == roleType
                        && str(t.get("conclusion")).toLowerCase().equals(c)) {
                    return true;
                }
            }
        }
        return false;
    }

    /** blocked conclusion 的回退岗位（无配置 null）。 */
    public Integer blockedFallbackRoleType() {
        Object fb = flow().get("blocked_fallback_role_type");
        return fb == null ? null : intOr(fb, -1);
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    private static int intOr(Object o, int fallback) {
        if (o instanceof Number n) {
            return n.intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(o));
        } catch (RuntimeException e) {
            return fallback;
        }
    }
}
