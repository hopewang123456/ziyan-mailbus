package io.github.hopewang123456.mailbus.auth;

import io.github.hopewang123456.mailbus.common.ApiException;

import java.util.Set;

public final class Authz {

    public static final String ALL = "*";
    public static final String MESSAGE_SEND = "message_send";
    public static final String MESSAGE_READ = "message_read";
    public static final String TASK_CREATE = "task_create";
    public static final String TASK_DISPATCH = "task_dispatch";
    public static final String RESULT_SUBMIT = "result_submit";
    public static final String HITL_REQUEST = "hitl_request";
    public static final String HITL_RESOLVE = "hitl_resolve";
    public static final String WORKFLOW_CREATE = "workflow_create";
    public static final String WORKFLOW_MODIFY = "workflow_modify";
    public static final String EMPLOYEE_INVITE = "employee_invite";
    public static final String EMPLOYEE_REMOVE = "employee_remove";
    public static final String AGENT_DEREGISTER = "agent_deregister";
    public static final String LOG_READ = "log_read";
    public static final String SYSTEM_CONFIG = "system_config";
    public static final String ORG_MANAGE = "org_manage";
    public static final String CONSOLE_ADMIN = "console_admin";

    private static final Set<String> ENDPOINT_GATED = Set.of(
            MESSAGE_SEND, TASK_DISPATCH, RESULT_SUBMIT);

    private Authz() {
    }

    public record Resource(String kind, String ownerId, String teamId, String path) {
        public static Resource of(String kind) {
            return new Resource(kind, null, null, null);
        }

        public static Resource owned(String kind, String ownerId) {
            return new Resource(kind, ownerId, null, null);
        }

        public static Resource team(String kind, String teamId) {
            return new Resource(kind, null, teamId, null);
        }
    }

    public static void require(Actor actor, String capability) {
        ensureAllowed(actor, capability, Resource.of("general"));
    }

    /** 仅要求账号可用；用于「登录即可、无特定能力」的写用例。 */
    public static void ensureActive(Actor actor) {
        if (!"active".equals(actor.status())) {
            throw ApiException.forbidden("账号未激活或已注销");
        }
    }

    public static void ensureAllowed(Actor actor, String capability, Resource resource) {
        if (!"active".equals(actor.status())) {
            throw ApiException.forbidden("账号未激活或已注销");
        }
        if (!actor.has(capability)) {
            throw ApiException.forbidden("缺少权限：" + capability);
        }
        if (!scopeAllows(actor, resource)) {
            throw ApiException.forbidden("超出数据可见范围");
        }
        if ("agent".equals(actor.accountType()) && ENDPOINT_GATED.contains(capability)
                && !actor.endpointApproved()) {
            throw ApiException.forbidden("Agent 端点尚未通过审核");
        }
    }

    public static void requireSelfOr(Actor actor, String employeeId, String capability) {
        if (!actor.employeeId().equals(employeeId)) {
            require(actor, capability);
        }
    }

    /** 多能力「或」语义：任一允许即通过，否则统一 403。 */
    public static void ensureAnyAllowed(Actor actor, Set<String> capabilities,
                                        Resource resource) {
        if (!"active".equals(actor.status())) {
            throw ApiException.forbidden("账号未激活或已注销");
        }
        boolean allowed = capabilities.stream().anyMatch(capability ->
                actor.has(capability)
                        && (!"agent".equals(actor.accountType())
                        || !ENDPOINT_GATED.contains(capability)
                        || actor.endpointApproved())
                        && scopeAllows(actor, resource));
        if (!allowed) {
            throw ApiException.forbidden("权限不足：需要 "
                    + String.join(" 或 ", capabilities));
        }
    }

    private static boolean scopeAllows(Actor actor, Resource resource) {
        String scope = actor.dataScope();
        if ("global".equals(scope)) {
            return true;
        }
        if ("team".equals(scope)) {
            if (resource.teamId() != null) {
                return resource.teamId().equals(actor.teamId());
            }
            if (resource.ownerId() != null) {
                return resource.ownerId().equals(actor.employeeId());
            }
            return true;
        }
        if (resource.teamId() != null) {
            return false;
        }
        if (resource.ownerId() != null) {
            return resource.ownerId().equals(actor.employeeId());
        }
        return true;
    }
}
