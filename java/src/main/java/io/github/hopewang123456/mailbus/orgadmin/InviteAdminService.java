package io.github.hopewang123456.mailbus.orgadmin;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.common.Tokens;
import io.github.hopewang123456.mailbus.config.AppProperties;
import io.github.hopewang123456.mailbus.identity.Employee;
import io.github.hopewang123456.mailbus.identity.EmployeeRepository;
import io.github.hopewang123456.mailbus.identity.EmployeeViews;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Set;

/** 真人邀请：签发、撤销、重发与公开接受（失效链接一律 410）。 */
@Service
public class InviteAdminService {

    private static final long DEFAULT_TTL_HOURS = 24;

    private record InviteData(String code, String accountType, String teamId, String positionId,
                              String dataScope, List<String> permissions, String createdBy,
                              Instant createdAt, Instant expiresAt, Instant consumedAt,
                              Instant revokedAt) {
    }

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final ObjectMapper objectMapper;
    private final EmployeeRepository employees;
    private final EmployeeViews views;
    private final AppProperties properties;

    public InviteAdminService(JdbcTemplate jdbc, Ids ids, ObjectMapper objectMapper,
                              EmployeeRepository employees, EmployeeViews views,
                              AppProperties properties) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.objectMapper = objectMapper;
        this.employees = employees;
        this.views = views;
        this.properties = properties;
    }

    @Transactional
    public OrgAdminDtos.InviteOut issue(Actor actor, OrgAdminDtos.EmployeeInviteIn input) {
        Set<String> requested = OrgAdminSupport.parsePermissions(input.permissions());
        OrgAdminSupport.ensureGrantable(actor, requested,
                input.dataScope() == null ? "self" : input.dataScope());
        Authz.ensureAllowed(actor, Authz.EMPLOYEE_INVITE,
                new Authz.Resource("team", null, input.teamId(), null));
        ensureReferences(input.teamId(), input.positionId());
        InviteData invite = insert("human", input.teamId(), input.positionId(),
                input.dataScope() == null ? "self" : input.dataScope(),
                OrgAdminSupport.sorted(requested), actor.employeeId(),
                input.expiresInHours() == null ? DEFAULT_TTL_HOURS : input.expiresInHours());
        return view(invite, true);
    }

    @Transactional
    public OrgAdminDtos.InviteOut revoke(Actor actor, String inviteId) {
        InviteData invite = load(inviteId);
        Authz.ensureAllowed(actor, Authz.EMPLOYEE_INVITE,
                new Authz.Resource("team", null, invite.teamId(), null));
        if (invite.consumedAt() != null) {
            throw ApiException.conflict("invalid_state", "邀请码已被使用，无法撤销");
        }
        if (invite.revokedAt() == null) {
            jdbc.update("""
                    UPDATE identity_invites SET revoked_at = ?, revoked_by = ?
                     WHERE invite_code = ? AND revoked_at IS NULL
                    """, Instant.now().getEpochSecond(), actor.employeeId(), invite.code());
        }
        return view(load(inviteId), false);
    }

    @Transactional
    public OrgAdminDtos.InviteOut resend(Actor actor, String inviteId) {
        InviteData old = load(inviteId);
        Authz.ensureAllowed(actor, Authz.EMPLOYEE_INVITE,
                new Authz.Resource("team", null, old.teamId(), null));
        if (old.consumedAt() != null) {
            throw ApiException.conflict("invalid_state", "邀请码已被使用，请重新创建邀请");
        }
        OrgAdminSupport.ensureGrantable(actor, Set.copyOf(old.permissions()), old.dataScope());
        ensureReferences(old.teamId(), old.positionId());
        if (old.revokedAt() == null) {
            jdbc.update("""
                    UPDATE identity_invites SET revoked_at = ?, revoked_by = ?
                     WHERE invite_code = ? AND revoked_at IS NULL
                    """, Instant.now().getEpochSecond(), actor.employeeId(), old.code());
        }
        InviteData fresh = insert(old.accountType(), old.teamId(), old.positionId(),
                old.dataScope(), old.permissions(), old.createdBy(), DEFAULT_TTL_HOURS);
        return view(fresh, true);
    }

    @Transactional
    public OrgAdminDtos.InviteAcceptOut accept(OrgAdminDtos.InviteAcceptIn input) {
        InviteData invite = load(input.inviteCode());
        Instant now = Instant.now();
        if (invite.revokedAt() != null || invite.consumedAt() != null) {
            throw ApiException.gone("invite_gone", "邀请链接已失效");
        }
        if (invite.expiresAt() != null && !invite.expiresAt().isAfter(now)) {
            throw ApiException.gone("invite_gone", "邀请链接已失效");
        }
        ensureInviter(invite);
        List<String> skills = List.of();
        if (invite.positionId() != null) {
            skills = positionSkills(invite.positionId());
        }
        String employeeId = ids.next("emp");
        String displayName = input.displayName() == null || input.displayName().isBlank()
                ? "新员工" : input.displayName().trim();
        Employee employee = new Employee(employeeId, displayName, invite.accountType(), "active",
                invite.teamId(), invite.positionId(), null, null,
                Set.copyOf(invite.permissions()), invite.dataScope(), List.of(), null, false,
                now, now);
        employees.save(employee);
        employees.saveSkills(employeeId, skills);
        int consumed = jdbc.update("""
                UPDATE identity_invites SET consumed_by = ?, consumed_at = ?
                 WHERE invite_code = ? AND consumed_at IS NULL AND revoked_at IS NULL
                """, employeeId, now.getEpochSecond(), invite.code());
        if (consumed == 0) {
            throw ApiException.gone("invite_gone", "邀请链接已失效");
        }
        return new OrgAdminDtos.InviteAcceptOut(views.view(employee), issueSession(employeeId, now));
    }

    private void ensureInviter(InviteData invite) {
        Employee inviter = invite.createdBy() == null ? null
                : employees.find(invite.createdBy()).orElse(null);
        if (inviter == null || "pending".equals(inviter.status())
                || "deregistered".equals(inviter.status())) {
            throw ApiException.forbidden("邀请人账号不可用");
        }
        if (!OrgAdminSupport.canGrant(inviter.capabilities(), invite.permissions())) {
            throw ApiException.forbidden("邀请人已无对应授权");
        }
        if (!OrgAdminSupport.scopeWithin(inviter.dataScope(), invite.dataScope())) {
            throw ApiException.forbidden("邀请人的数据范围已收缩");
        }
    }

    private InviteData insert(String accountType, String teamId, String positionId,
                              String dataScope, List<String> permissions, String createdBy,
                              long ttlHours) {
        Instant now = Instant.now();
        String code = ids.next("inv");
        jdbc.update("""
                INSERT INTO identity_invites
                    (invite_code, account_type, team_id, position_id, data_scope, permissions,
                     created_by, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, code, accountType, teamId, positionId, dataScope,
                OrgAdminSupport.toJson(objectMapper, permissions), createdBy,
                now.getEpochSecond(), now.plusSeconds(ttlHours * 3600).getEpochSecond());
        return load(code);
    }

    private InviteData load(String code) {
        return jdbc.query("SELECT * FROM identity_invites WHERE invite_code = ?",
                        (row, index) -> new InviteData(
                                row.getString("invite_code"), row.getString("account_type"),
                                row.getString("team_id"), row.getString("position_id"),
                                row.getString("data_scope"),
                                OrgAdminSupport.parseJsonArray(objectMapper,
                                        row.getString("permissions")),
                                row.getString("created_by"),
                                OrgAdminSupport.instant(row, "created_at"),
                                OrgAdminSupport.instant(row, "expires_at"),
                                OrgAdminSupport.instant(row, "consumed_at"),
                                OrgAdminSupport.instant(row, "revoked_at")), code)
                .stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("邀请不存在"));
    }

    private void ensureReferences(String teamId, String positionId) {
        if (teamId != null) {
            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM org_teams WHERE team_id = ?", Integer.class, teamId);
            if (count == null || count == 0) {
                throw ApiException.notFound("团队不存在");
            }
        }
        if (positionId != null) {
            positionSkills(positionId);
        }
    }

    private List<String> positionSkills(String positionId) {
        List<String> rows = jdbc.queryForList(
                "SELECT capabilities FROM org_positions WHERE position_id = ?",
                String.class, positionId);
        if (rows.isEmpty()) {
            throw ApiException.notFound("岗位不存在");
        }
        return OrgAdminSupport.parseJsonArray(objectMapper, rows.get(0));
    }

    private OrgAdminDtos.InviteOut view(InviteData invite, boolean plaintext) {
        return new OrgAdminDtos.InviteOut(invite.code(), plaintext ? invite.code() : null,
                invite.accountType(), invite.teamId(), invite.positionId(), invite.dataScope(),
                OrgAdminSupport.sorted(invite.permissions()), invite.createdBy(),
                invite.createdAt(), invite.expiresAt(), invite.consumedAt(), invite.revokedAt());
    }

    private String issueSession(String employeeId, Instant now) {
        String token = ids.token();
        Instant expiresAt = now.plusSeconds(properties.sessionDays() * 86400L);
        jdbc.update("""
                INSERT INTO identity_sessions (token_hash, employee_id, issued_at, expires_at)
                VALUES (?, ?, ?, ?)
                """, Tokens.hash(token), employeeId, now.getEpochSecond(),
                expiresAt.getEpochSecond());
        return token;
    }
}
