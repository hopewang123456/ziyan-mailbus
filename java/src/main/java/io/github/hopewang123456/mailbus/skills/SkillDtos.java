package io.github.hopewang123456.mailbus.skills;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;

public final class SkillDtos {

    private SkillDtos() {
    }

    public record SkillPackageIn(@NotBlank @Size(max = 64) String name,
                                 @NotBlank @Pattern(regexp = "local|http") String sourceType,
                                 @NotBlank @Size(max = 512) String sourceUri,
                                 @Size(max = 64) String entry,
                                 @Size(max = 512) String note) {
    }

    public record SkillBindingIn(@NotBlank @Pattern(regexp = "agent|employee") String targetType,
                                 @NotBlank @Size(max = 64) String targetId,
                                 Boolean enabled) {
    }

    public record SkillBindingOut(String targetType, String targetId, boolean enabled) {
    }

    public record SkillPackageOut(String packageId, String name, String sourceType,
                                  String sourceUri, String entry, String version,
                                  boolean enabled, String note, Instant lastCheckedAt,
                                  String lastError, Instant createdAt, Instant updatedAt,
                                  List<SkillBindingOut> bindings) {
        public SkillPackageOut withBindings(List<SkillBindingOut> next) {
            return new SkillPackageOut(packageId, name, sourceType, sourceUri, entry, version,
                    enabled, note, lastCheckedAt, lastError, createdAt, updatedAt, next);
        }
    }

    public record EffectiveSkillOut(String packageId, String name, String sourceType,
                                    String sourceUri, String entry, String version,
                                    boolean enabled, String note, String origin) {
    }
}
