package io.github.hopewang123456.mailbus.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

@ConfigurationProperties(prefix = "mailbus")
public record AppProperties(
        String dataDir,
        int sessionDays,
        long heartbeatTimeoutSeconds,
        long heartbeatSweepSeconds,
        long dispatchIntervalSeconds,
        int dispatchBatch,
        int dispatchMaxAttempts,
        String layoutPath,
        String metricsManifestPath
) {
    public AppProperties {
        if (dataDir == null || dataDir.isBlank()) {
            dataDir = "../data";
        }
        if (sessionDays <= 0) {
            sessionDays = 7;
        }
        if (heartbeatTimeoutSeconds <= 0) {
            heartbeatTimeoutSeconds = 180;
        }
        if (heartbeatSweepSeconds <= 0) {
            heartbeatSweepSeconds = 30;
        }
        if (dispatchIntervalSeconds <= 0) {
            dispatchIntervalSeconds = 5;
        }
        if (dispatchBatch <= 0) {
            dispatchBatch = 50;
        }
        if (dispatchMaxAttempts <= 0) {
            dispatchMaxAttempts = 3;
        }
        if (layoutPath == null || layoutPath.isBlank()) {
            layoutPath = "../config/office-layout.json";
        }
        if (metricsManifestPath == null || metricsManifestPath.isBlank()) {
            metricsManifestPath = "../shared/config/mailbus/metrics-manifest.json";
        }
    }

    public Path dataDirPath() {
        return Path.of(dataDir);
    }

    public Path layoutPathFile() {
        return Path.of(layoutPath);
    }

    public Path metricsManifestFile() {
        return Path.of(metricsManifestPath);
    }

    public Path dbPath() {
        return dataDirPath().resolve("mailbus.db");
    }

    public Path settingsStorePath() {
        return dataDirPath().resolve("settings.json");
    }

    public Path fileBusDir() {
        return dataDirPath().resolve("file_bus");
    }

    public Path artifactsDir() {
        Path dir = dataDirPath().resolve("artifacts");
        try {
            Files.createDirectories(dir);
        } catch (IOException e) {
            throw new IllegalStateException("无法创建产物目录", e);
        }
        return dir;
    }

    public Path mcpDir() {
        return dataDirPath().resolve("mcp");
    }
}
