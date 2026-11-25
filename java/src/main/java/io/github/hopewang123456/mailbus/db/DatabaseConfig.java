package io.github.hopewang123456.mailbus.db;

import io.github.hopewang123456.mailbus.config.AppProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.sqlite.SQLiteConfig;
import org.sqlite.SQLiteDataSource;

import javax.sql.DataSource;
import java.io.IOException;
import java.nio.file.Files;

@Configuration
public class DatabaseConfig {

    @Bean
    public DataSource dataSource(AppProperties properties) throws IOException {
        Files.createDirectories(properties.dataDirPath());
        SQLiteConfig config = new SQLiteConfig();
        config.setJournalMode(SQLiteConfig.JournalMode.WAL);
        config.enforceForeignKeys(true);
        config.setBusyTimeout(5000);
        // WAL 下 NORMAL 已能保证崩溃一致性，减少每次提交的 fsync 开销。
        config.setSynchronous(SQLiteConfig.SynchronousMode.NORMAL);
        SQLiteDataSource dataSource = new SQLiteDataSource(config);
        dataSource.setUrl("jdbc:sqlite:" + properties.dbPath());
        return dataSource;
    }

    @Bean
    public MigrationRunner migrationRunner(DataSource dataSource) {
        return new MigrationRunner(dataSource);
    }
}
