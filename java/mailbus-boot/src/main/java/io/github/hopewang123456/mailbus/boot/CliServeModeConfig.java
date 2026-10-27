package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.cli.MailbusCommand;
import org.springframework.boot.CommandLineRunner;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import picocli.CommandLine;

/**
 * Dual-mode entry: bare run (or --spring args) starts serve; a first non-flag
 * argument dispatches as a CLI subcommand and exits with its code
 * (python `mailbus serve` vs `mailbus send ...` semantics).
 *
 * P0a: picocli-spring-boot-starter has no Spring Boot 4 build (upstream issue
 * #2491, maintainer recommends wiring picocli core yourself), so the Spring
 * bridge is the thin IFactory below.
 */
@Configuration
public class CliServeModeConfig {

    /** Resolve subcommand instances as Spring beans when registered, else default. */
    static final class SpringCliFactory implements CommandLine.IFactory {
        private final ApplicationContext ctx;

        SpringCliFactory(ApplicationContext ctx) {
            this.ctx = ctx;
        }

        @Override
        public <K> K create(Class<K> cls) throws Exception {
            try {
                return ctx.getBean(cls);
            } catch (NoSuchBeanDefinitionException e) {
                return CommandLine.defaultFactory().create(cls);
            }
        }
    }

    @Bean
    public CommandLine commandLine(MailbusCommand rootCommand, ApplicationContext ctx) {
        return new CommandLine(rootCommand, new SpringCliFactory(ctx));
    }

    @Bean
    CommandLineRunner cliDispatch(CommandLine commandLine) {
        return args -> {
            // Spring-style options (--mailbus.data-dir=..., --spring.x.y=z) stay with Spring;
            // dotted long options are never picocli subcommand options.
            String[] cliArgs = java.util.Arrays.stream(args)
                    .filter(a -> !(a.startsWith("--") && a.indexOf('.', 2) > 0))
                    .toArray(String[]::new);
            if (cliArgs.length > 0 && !cliArgs[0].startsWith("-")) {
                int exitCode = commandLine.execute(cliArgs);
                System.exit(exitCode);
            }
        };
    }
}
