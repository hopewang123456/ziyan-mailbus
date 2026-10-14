package io.github.hopewang123456.mailbus.boot.arch;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;

/**
 * Layering gates — enforced from day one (the Python audit found 10 manual-
 * convention violations; here the CI fails the build instead).
 * Mirrors ARCHITECTURE.md dependency rules; mailbus-boot is the composition
 * root and may depend on everything.
 */
class LayeredArchitectureTest {

    private static JavaClasses classes;

    @BeforeAll
    static void importClasses() {
        classes = new ClassFileImporter()
                .withImportOption(new ImportOption.DoNotIncludeTests())
                .importPackages("io.github.hopewang123456.mailbus");
    }

    @Test
    void layeredArchitectureIsEnforced() {
        layeredArchitecture().consideringOnlyDependenciesInLayers()
                .layer("Domain").definedBy("..mailbus.domain..")
                .layer("Ports").definedBy("..mailbus.ports..")
                .layer("App").definedBy("..mailbus.app..")
                .layer("Adapters").definedBy("..mailbus.adapters..")
                .layer("Infra").definedBy("..mailbus.infra..")
                .layer("Api").definedBy("..mailbus.api..")
                .layer("Cli").definedBy("..mailbus.cli..")
                .layer("Boot").definedBy("..mailbus.boot..")
                .whereLayer("Boot").mayNotBeAccessedByAnyLayer()
                .whereLayer("Api").mayOnlyBeAccessedByLayers("Boot")
                .whereLayer("Cli").mayOnlyBeAccessedByLayers("Boot")
                .whereLayer("Adapters").mayOnlyBeAccessedByLayers("Boot")
                .whereLayer("Infra").mayOnlyBeAccessedByLayers("Boot", "Api", "Cli", "App", "Adapters")
                .whereLayer("App").mayOnlyBeAccessedByLayers("Boot", "Api", "Cli")
                .whereLayer("Ports").mayOnlyBeAccessedByLayers("Boot", "Api", "Cli", "App", "Adapters")
                .whereLayer("Domain").mayOnlyBeAccessedByLayers("Boot", "Api", "Cli", "App", "Adapters", "Ports", "Infra")
                .check(classes);
    }

    @Test
    void domainHasZeroSpringDependencies() {
        noClasses().that().resideInAPackage("..mailbus.domain..")
                .should().dependOnClassesThat().resideInAPackage("org.springframework..")
                .check(classes);
    }

    @Test
    void appMustNotImportAdapters() {
        // Python rule: application MUST NOT import adapters concrete modules.
        noClasses().that().resideInAPackage("..mailbus.app..")
                .should().dependOnClassesThat().resideInAPackage("..mailbus.adapters..")
                .check(classes);
    }
}
