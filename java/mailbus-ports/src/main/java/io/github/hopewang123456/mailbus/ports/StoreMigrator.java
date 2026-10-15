package io.github.hopewang123456.mailbus.ports;

import io.github.hopewang123456.mailbus.domain.message.MsgRecord;

import java.util.List;

/**
 * Port: reads a legacy (Python) store and yields normalized records with
 * preserved raw bodies. Implemented by the migration adapter.
 */
public interface StoreMigrator {

    record RawMessage(MsgRecord record, String rawJson, List<String> warnings) {}

    record Result(List<RawMessage> messages, List<String> warnings, int agentsSeen) {}

    Result readAll();

    /** Per-invocation factory: the python root comes from the CLI argument. */
    interface Factory {
        StoreMigrator forRoot(java.nio.file.Path pythonStoreRoot);
    }
}
