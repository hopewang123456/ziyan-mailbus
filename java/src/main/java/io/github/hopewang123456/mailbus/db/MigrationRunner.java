package io.github.hopewang123456.mailbus.db;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.Resource;
import org.springframework.jdbc.datasource.init.ScriptUtils;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * 与 Python 版保持同一 schema 版本表与执行语义：按文件名前缀排序，事务内执行并登记版本。
 */
public class MigrationRunner implements InitializingBean {

    private final DataSource dataSource;
    private int schemaVersion;

    public MigrationRunner(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public void afterPropertiesSet() {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(true);
            try (Statement statement = connection.createStatement()) {
                statement.execute("""
                        CREATE TABLE IF NOT EXISTS ops_schema_version (
                            version    INTEGER PRIMARY KEY,
                            applied_at TEXT NOT NULL
                        )
                        """);
            }
            Set<Integer> applied = appliedVersions(connection);
            List<String> scripts = scripts();
            for (String script : scripts) {
                int version = Integer.parseInt(script.substring(0, script.indexOf('_')));
                if (!applied.contains(version)) {
                    apply(connection, script, version);
                    applied.add(version);
                }
            }
            schemaVersion = applied.stream().mapToInt(Integer::intValue).max().orElse(0);
        } catch (Exception exception) {
            throw new IllegalStateException("数据库迁移失败", exception);
        }
    }

    public int schemaVersion() {
        return schemaVersion;
    }

    private Set<Integer> appliedVersions(Connection connection) throws SQLException {
        Set<Integer> applied = new HashSet<>();
        try (Statement statement = connection.createStatement();
             ResultSet rows = statement.executeQuery("SELECT version FROM ops_schema_version")) {
            while (rows.next()) {
                applied.add(rows.getInt(1));
            }
        }
        return applied;
    }

    private List<String> scripts() throws Exception {
        Resource[] resources = new PathMatchingResourcePatternResolver()
                .getResources("classpath*:db/migration/*.sql");
        List<String> names = new ArrayList<>();
        for (Resource resource : resources) {
            names.add(resource.getFilename());
        }
        names.sort(Comparator.naturalOrder());
        return names;
    }

    private void apply(Connection connection, String name, int version) throws SQLException {
        connection.setAutoCommit(false);
        try {
            Resource resource = new ClassPathResource("db/migration/" + name);
            ScriptUtils.executeSqlScript(connection, resource);
            try (PreparedStatement insert = connection.prepareStatement(
                    "INSERT INTO ops_schema_version (version, applied_at) VALUES (?, datetime('now'))")) {
                insert.setInt(1, version);
                insert.executeUpdate();
            }
            connection.commit();
        } catch (Exception exception) {
            connection.rollback();
            throw new SQLException("迁移 " + name + " 失败", exception);
        } finally {
            connection.setAutoCommit(true);
        }
    }
}
