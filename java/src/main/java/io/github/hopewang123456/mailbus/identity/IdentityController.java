package io.github.hopewang123456.mailbus.identity;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import io.github.hopewang123456.mailbus.org.OrgDtos;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/identity")
@Validated
public class IdentityController {

    private final IdentityService service;

    public IdentityController(IdentityService service) {
        this.service = service;
    }

    @GetMapping("/bootstrap")
    public IdentityDtos.BootstrapStatusOut bootstrap() {
        return service.bootstrapStatus();
    }

    @PostMapping("/bootstrap/super-admin")
    @ResponseStatus(HttpStatus.CREATED)
    public IdentityDtos.SessionOut superAdmin(@Valid @RequestBody IdentityDtos.SuperAdminIn input) {
        return service.createSuperAdmin(input);
    }

    @PostMapping("/bootstrap/model-config")
    public IdentityDtos.BootstrapStatusOut modelConfig(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody IdentityDtos.ModelConfigIn input) {
        return service.configureModel(actor, input);
    }

    @PostMapping("/bootstrap/team")
    public OrgDtos.TeamOut firstTeam(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody OrgDtos.TeamIn input) {
        return service.createFirstTeam(actor, input);
    }

    @PostMapping("/bootstrap/{step}/skip")
    public IdentityDtos.BootstrapStatusOut skip(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String step) {
        return service.skip(actor, step);
    }

    @GetMapping("/staff")
    public List<IdentityDtos.EmployeeView> staff(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(defaultValue = "pending")
            @Pattern(regexp = "pending|active|all") String status) {
        return service.listStaff(actor, status);
    }

    @PostMapping("/staff")
    @ResponseStatus(HttpStatus.CREATED)
    public IdentityDtos.ApplyOut apply(@Valid @RequestBody IdentityDtos.ApplyIn input) {
        return service.apply(input);
    }

    @GetMapping("/staff/{employee_id}")
    public IdentityDtos.EmployeeView staffDetail(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("employee_id") String employeeId) {
        return service.get(actor, employeeId);
    }

    @PostMapping("/staff/{employee_id}/review")
    public IdentityDtos.EmployeeView review(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("employee_id") String employeeId,
            @Valid @RequestBody IdentityDtos.ReviewIn input) {
        return service.review(actor, employeeId, input);
    }

    @PostMapping("/staff/{employee_id}/activate")
    public IdentityDtos.SessionOut activate(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("employee_id") String employeeId) {
        return service.activate(actor, employeeId);
    }

    @PostMapping("/staff/{employee_id}/heartbeat")
    public IdentityDtos.EmployeeView heartbeat(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("employee_id") String employeeId) {
        return service.heartbeat(actor, employeeId);
    }

    @PostMapping("/staff/{employee_id}/deregister")
    public IdentityDtos.EmployeeView deregister(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("employee_id") String employeeId,
            @RequestBody(required = false) IdentityDtos.DeregisterIn input) {
        return service.deregister(actor, employeeId, input == null ? null : input.reason());
    }

    @PatchMapping("/staff/{employee_id}/seat")
    public IdentityDtos.EmployeeView seat(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("employee_id") String employeeId,
            @RequestBody IdentityDtos.SeatAssignIn input) {
        return service.setSeat(actor, employeeId, input.seatId());
    }

    @PatchMapping("/staff/{employee_id}/endpoint")
    public IdentityDtos.EmployeeView endpoint(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("employee_id") String employeeId,
            @Valid @RequestBody IdentityDtos.EndpointReviewIn input) {
        return service.reviewEndpoint(actor, employeeId, Boolean.TRUE.equals(input.approved()));
    }

    @PatchMapping("/staff/{employee_id}/manager")
    public IdentityDtos.EmployeeView manager(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("employee_id") String employeeId,
            @Valid @RequestBody IdentityDtos.ManagerIn input) {
        return service.setManager(actor, employeeId, Boolean.TRUE.equals(input.enabled()));
    }

    @PatchMapping("/staff/{employee_id}/agent")
    public IdentityDtos.EmployeeView agent(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("employee_id") String employeeId,
            @RequestBody IdentityDtos.AgentBindIn input) {
        return service.bindAgent(actor, employeeId, input.agentId());
    }

    @PostMapping("/invites")
    @ResponseStatus(HttpStatus.CREATED)
    public IdentityDtos.InviteOut invite(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody IdentityDtos.InviteIn input) {
        return service.issueInvite(actor, input);
    }

    @GetMapping("/me")
    public IdentityDtos.EmployeeView me(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return service.me(actor);
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(
            @RequestHeader("Authorization") String authorization) {
        String token = authorization.startsWith("Bearer ")
                ? authorization.substring(7).trim() : "";
        service.logout(token);
        return ResponseEntity.status(HttpStatus.NO_CONTENT).build();
    }
}
