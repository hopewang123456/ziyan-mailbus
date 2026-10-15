package io.github.hopewang123456.mailbus.ports;

import java.nio.file.Path;
import java.util.List;

/** Port: import agent cards from a python repo's transport cards. */
public interface AgentCardImporter {

    record Import(AgentDirectory.AgentCard card, String note) {}

    List<Import> importFrom(Path repoRoot);

    /** Per-invocation factory: repo root comes from the CLI argument. */
    interface Factory {
        AgentCardImporter forRoot(Path repoRoot);
    }
}
