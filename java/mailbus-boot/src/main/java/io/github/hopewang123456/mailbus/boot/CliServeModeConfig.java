package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.cli.MailbusCommand;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import picocli.CommandLine;
import picocli.spring.PicocliSpringFactory;

/**
 * Dual-mode entry: bare run (or --spring args) starts serve; a first non-flag
 * argument dispatches as a CLI subcommand and exits with its code
 * (python `mailbus serve` vs `mailbus send ...` semantics).
 *
 * The CommandLine bean is declared manually because picocli-spring-boot-starter
 * 4.7.x registers its autoconfiguration via spring.factories, which Spring
 * Boot 3 no longer picks up.
 */
@Configuration
public class CliServeModeConfig {

    @Bean
    public CommandLine commandLine(MailbusCommand rootCommand, ApplicationContext ctx) {
        return new CommandLine(rootCommand, new PicocliSpringFactory(ctx));
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
