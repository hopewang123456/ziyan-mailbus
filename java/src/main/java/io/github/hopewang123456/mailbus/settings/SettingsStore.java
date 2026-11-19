package io.github.hopewang123456.mailbus.settings;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.config.AppProperties;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.LinkedHashMap;
import java.util.Map;

/** data/settings.json：插件清单与运行 env，写法与 Python 版本一致。 */
@Component
public class SettingsStore {

    private final Path path;
    private final ObjectMapper objectMapper;

    public SettingsStore(AppProperties properties, ObjectMapper objectMapper) {
        this.path = properties.settingsStorePath();
        this.objectMapper = objectMapper;
    }

    public synchronized Map<String, Object> read() {
        try {
            if (!Files.isRegularFile(path)) {
                return new LinkedHashMap<>();
            }
            Map<String, Object> data = objectMapper.readValue(path.toFile(),
                    new TypeReference<Map<String, Object>>() {
                    });
            return data == null ? new LinkedHashMap<>() : data;
        } catch (Exception exception) {
            return new LinkedHashMap<>();
        }
    }

    public synchronized void write(Map<String, Object> data) {
        try {
            if (path.getParent() != null) {
                Files.createDirectories(path.getParent());
            }
            Path temp = path.resolveSibling(path.getFileName() + ".tmp");
            Files.writeString(temp, objectMapper.writerWithDefaultPrettyPrinter()
                    .writeValueAsString(data));
            Files.move(temp, path, StandardCopyOption.REPLACE_EXISTING);
        } catch (Exception exception) {
            throw new IllegalStateException("写入运行配置失败", exception);
        }
    }
}
