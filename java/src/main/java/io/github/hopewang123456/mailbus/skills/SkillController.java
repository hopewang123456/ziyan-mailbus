package io.github.hopewang123456.mailbus.skills;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
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
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/skills")
@Validated
public class SkillController {

    private final SkillService service;

    public SkillController(SkillService service) {
        this.service = service;
    }

    @GetMapping
    public List<SkillDtos.SkillPackageOut> list() {
        return service.list();
    }

    @GetMapping("/effective")
    public List<SkillDtos.EffectiveSkillOut> effective(
            @RequestParam("target_type")
            @Pattern(regexp = "agent|employee") String targetType,
            @RequestParam("target_id") String targetId) {
        return service.effective(targetType, targetId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public SkillDtos.SkillPackageOut create(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody SkillDtos.SkillPackageIn input) {
        return service.create(actor, input);
    }

    @PatchMapping("/{package_id}")
    public SkillDtos.SkillPackageOut update(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("package_id") String packageId,
            @RequestBody Map<String, Object> changes) {
        return service.update(actor, packageId, changes);
    }

    @PostMapping("/{package_id}/refresh")
    public SkillDtos.SkillPackageOut refresh(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("package_id") String packageId) {
        return service.refresh(actor, packageId);
    }

    @PostMapping("/{package_id}/delete")
    public ResponseEntity<Void> delete(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("package_id") String packageId) {
        service.delete(actor, packageId);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/{package_id}/bindings")
    public SkillDtos.SkillPackageOut bind(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("package_id") String packageId,
            @Valid @RequestBody SkillDtos.SkillBindingIn input) {
        return service.bind(actor, packageId, input);
    }
}
