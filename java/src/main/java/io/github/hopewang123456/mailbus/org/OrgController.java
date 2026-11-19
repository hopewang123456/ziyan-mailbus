package io.github.hopewang123456.mailbus.org;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/org")
public class OrgController {

    private final OrgService service;

    public OrgController(OrgService service) {
        this.service = service;
    }

    @GetMapping("/teams")
    public List<OrgDtos.TeamOut> teams() {
        return service.teams();
    }

    @PostMapping("/teams")
    @ResponseStatus(HttpStatus.CREATED)
    public OrgDtos.TeamOut createTeam(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody OrgDtos.TeamIn input) {
        return service.createTeam(actor, input);
    }

    @GetMapping("/positions")
    public List<OrgDtos.PositionOut> positions() {
        return service.positions();
    }

    @PostMapping("/positions")
    @ResponseStatus(HttpStatus.CREATED)
    public OrgDtos.PositionOut createPosition(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody OrgDtos.PositionIn input) {
        return service.createPosition(actor, input);
    }

    @GetMapping("/seats")
    public List<OrgDtos.OrgSeatOut> seats() {
        return service.seats();
    }

    @PatchMapping("/seats/{seat_id}")
    public OrgDtos.OrgSeatOut updateSeat(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("seat_id") String seatId,
            @RequestBody OrgDtos.SeatUpdateIn input) {
        return service.updateSeat(actor, seatId, input);
    }
}
