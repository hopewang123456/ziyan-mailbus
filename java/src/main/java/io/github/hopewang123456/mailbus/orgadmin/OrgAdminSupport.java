package io.github.hopewang123456.mailbus.orgadmin;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.common.ApiException;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

/** 组织域共享规则：权限枚举、授权上界、标签清洗与 JSON 转换。 */
final class OrgAdminSupport {

    static final Set<String> PERMISSIONS = Set.of(
            "message_send", "message_read", "task_create", "task_dispatch", "result_submit",
            "hitl_request", "hitl_resolve", "workflow_create", "workflow_modify",
            "employee_invite", "employee_remove", "agent_deregister", "log_read",
            "system_config", "org_manage", "console_admin", "role_manage", "role_bind",
            "workflow_publish", "escalation_resolve", "artifact_read_all", "*");

    private OrgAdminSupport() {
    }

    static List<String> sorted(Collection<String> values) {
        return new ArrayList<>(new TreeSet<>(values));
    }

    static List<String> distinct(List<String> values) {
        return new ArrayList<>(new LinkedHashSet<>(values == null ? List.of() : values));
    }

    static List<String> parseJsonArray(ObjectMapper objectMapper, String value) {
        try {
            List<String> parsed = objectMapper.readValue(value == null ? "[]" : value,
                    new TypeReference<List<String>>() {
                    });
            return parsed == null ? List.of() : parsed;
        } catch (Exception exception) {
            return List.of();
        }
    }

    static String toJson(ObjectMapper objectMapper, Collection<String> values) {
        try {
            return objectMapper.writeValueAsString(values);
        } catch (Exception exception) {
            return "[]";
        }
    }

    /** 业务技能标签：去空白、去重、丢弃空串。 */
    static List<String> cleanTags(Collection<String> values) {
        List<String> cleaned = new ArrayList<>();
        for (String value : values == null ? List.<String>of() : values) {
            if (value == null) {
                continue;
            }
            String trimmed = value.trim();
            if (!trimmed.isEmpty() && !cleaned.contains(trimmed)) {
                cleaned.add(trimmed);
            }
        }
        return cleaned;
    }

    static List<String> requireTags(Collection<String> values) {
        List<String> cleaned = cleanTags(values);
        if (cleaned.stream().anyMatch(value -> value.length() > 64)) {
            throw ApiException.conflict("invalid_state", "业务技能标签不能超过 64 个字符");
        }
        return cleaned;
    }

    /** 员工技能标签在 Python 端使用 422，岗位在 structure 使用 409，故分开。 */
    static List<String> requireEmployeeTags(Collection<String> values) {
        List<String> cleaned = cleanTags(values);
        if (cleaned.stream().anyMatch(value -> value.length() > 64)) {
            throw ApiException.unprocessable("unprocessable", "业务技能标签不能超过 64 个字符");
        }
        return cleaned;
    }

    static Set<String> parsePermissions(Collection<String> values) {
        Set<String> requested = new LinkedHashSet<>();
        for (String value : values == null ? List.<String>of() : values) {
            if (!PERMISSIONS.contains(value)) {
                throw ApiException.unprocessable("unprocessable", "存在未知权限值");
            }
            requested.add(value);
        }
        return requested;
    }

    /** 邀请/授权上界：权限子集 + 范围不越级；console_admin、全量权限与 global 范围仅超管可授。 */
    static void ensureGrantable(Actor actor, Set<String> requested, String targetScope) {
        Set<String> actorCaps = actor.capabilities();
        boolean superAdmin = actorCaps.contains("*");
        if (!superAdmin && (requested.contains("*") || !actorCaps.containsAll(requested))) {
            throw ApiException.forbidden("不能授予超出自身范围的权限");
        }
        if (!superAdmin && (requested.contains("console_admin") || requested.contains("*"))) {
            throw ApiException.forbidden("console_admin 与全量权限仅超级管理员可授予");
        }
        if ("global".equals(targetScope) && !superAdmin) {
            throw ApiException.forbidden("global 数据范围仅超级管理员可授予");
        }
        if (!scopeWithin(actor.dataScope(), targetScope)) {
            throw ApiException.forbidden("不能授予超出自身范围的数据可见范围");
        }
    }

    static void ensureScopeGrantable(Actor actor, String targetScope) {
        ensureGrantable(actor, Set.of(), targetScope);
    }

    static boolean scopeWithin(String actorScope, String targetScope) {
        return rank(targetScope) <= rank(actorScope);
    }

    private static int rank(String scope) {
        if ("global".equals(scope)) {
            return 2;
        }
        if ("team".equals(scope)) {
            return 1;
        }
        return 0;
    }

    static boolean canGrant(Collection<String> grantor, Collection<String> requested) {
        if (grantor.contains("*")) {
            return true;
        }
        return !requested.contains("*") && grantor.containsAll(requested);
    }

    static Instant instant(ResultSet row, String column) throws SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : Instant.ofEpochSecond((long) value);
    }

    static Double boxedDouble(ResultSet row, String column) throws SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : value;
    }
}
