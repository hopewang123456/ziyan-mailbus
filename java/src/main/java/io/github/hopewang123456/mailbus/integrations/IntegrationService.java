package io.github.hopewang123456.mailbus.integrations;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.settings.SettingsStore;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class IntegrationService {

    private static final List<IntegrationDtos.IntegrationItemOut> CATALOG = List.of(
            new IntegrationDtos.IntegrationItemOut("comfyui", "image",
                    "ComfyUI 图像生成", List.of("probe", "txt2img")),
            new IntegrationDtos.IntegrationItemOut("n8n", "automation",
                    "n8n 自动化编排", List.of("probe")),
            new IntegrationDtos.IntegrationItemOut("agentmemory", "memory",
                    "AgentMemory 共享记忆", List.of("probe")),
            new IntegrationDtos.IntegrationItemOut("gpu", "compute",
                    "GPU 资源探测", List.of("probe")));
    private static final String NOTE =
            "内置集成只做探测合同；插件与 env 持久化在 data/settings.json";

    private final SettingsStore store;

    public IntegrationService(SettingsStore store) {
        this.store = store;
    }

    public IntegrationDtos.IntegrationsOut listIntegrations() {
        return new IntegrationDtos.IntegrationsOut(CATALOG, plugins(store.read()), NOTE);
    }

    public IntegrationDtos.PluginActionOut mutatePlugins(Actor actor, String action,
                                                         String spec) {
        Authz.ensureAllowed(actor, Authz.SYSTEM_CONFIG, Authz.Resource.of("integration"));
        String name = spec == null ? "" : spec.strip();
        if (name.isEmpty()) {
            throw ApiException.conflict("invalid_state", "插件标识不能为空");
        }
        Map<String, Object> data = store.read();
        List<String> plugins = plugins(data);
        if ("add_plugin".equals(action)) {
            if (!plugins.contains(name)) {
                plugins.add(name);
            }
        } else if ("remove_plugin".equals(action)) {
            plugins.removeIf(name::equals);
        } else {
            throw ApiException.conflict("invalid_state",
                    "action 只支持 add_plugin / remove_plugin");
        }
        data.put("plugins", plugins);
        store.write(data);
        return new IntegrationDtos.PluginActionOut(plugins);
    }

    public Map<String, Object> invoke(Actor actor, String name, String action,
                                      Map<String, Object> params) {
        Authz.ensureAllowed(actor, Authz.SYSTEM_CONFIG, Authz.Resource.of("integration"));
        IntegrationDtos.IntegrationItemOut entry = CATALOG.stream()
                .filter(item -> item.name().equals(name)).findFirst()
                .orElseThrow(() -> ApiException.notFound("集成不存在"));
        if (!entry.actions().contains(action)) {
            throw ApiException.conflict("invalid_state",
                    "集成 " + name + " 不支持动作 " + action);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("ok", false);
        result.put("name", name);
        result.put("action", action);
        result.put("error", "not_configured");
        if ("txt2img".equals(action)) {
            result.put("prompt", text(params.get("prompt")));
        } else {
            result.put("detail", "尚未配置外部地址，仅返回探测合同");
        }
        return result;
    }

    public IntegrationDtos.EnvGroupsOut envGroups() {
        Map<String, Object> values = env(store.read());
        Map<String, List<IntegrationDtos.EnvEntryOut>> groups = new LinkedHashMap<>();
        groups.put("agentmemory", List.of(entry(values, "AGENTMEMORY_URL",
                "共享记忆服务地址", false)));
        groups.put("openclaw", List.of(entry(values, "OPENCLAW_GATEWAY_TOKEN",
                "OpenClaw Gateway Token", true)));
        return new IntegrationDtos.EnvGroupsOut(groups);
    }

    public IntegrationDtos.EnvGroupsOut updateEnv(Actor actor, Map<String, String> values) {
        Authz.ensureAllowed(actor, Authz.SYSTEM_CONFIG, Authz.Resource.of("integration"));
        List<String> unknown = values.keySet().stream()
                .filter(key -> !"AGENTMEMORY_URL".equals(key)
                        && !"OPENCLAW_GATEWAY_TOKEN".equals(key))
                .sorted().toList();
        if (!unknown.isEmpty()) {
            throw ApiException.conflict("invalid_state",
                    "不支持的配置项：" + String.join(", ", unknown));
        }
        Map<String, Object> data = store.read();
        Map<String, Object> env = env(data);
        for (Map.Entry<String, String> item : values.entrySet()) {
            String text = item.getValue() == null ? "" : item.getValue().strip();
            if (text.isEmpty()) {
                env.remove(item.getKey());
            } else {
                env.put(item.getKey(), text);
            }
        }
        data.put("env", env);
        store.write(data);
        return envGroups();
    }

    public IntegrationDtos.ReloadOut reload(Actor actor) {
        Authz.ensureAllowed(actor, Authz.SYSTEM_CONFIG, Authz.Resource.of("integration"));
        return new IntegrationDtos.ReloadOut(true, plugins(store.read()));
    }

    private IntegrationDtos.EnvEntryOut entry(Map<String, Object> values, String key,
                                              String label, boolean secret) {
        String stored = text(values.get(key));
        return new IntegrationDtos.EnvEntryOut(key, label, secret ? "" : stored,
                !stored.isEmpty());
    }

    private List<String> plugins(Map<String, Object> data) {
        List<String> result = new ArrayList<>();
        if (data.get("plugins") instanceof List<?> items) {
            for (Object item : items) {
                if (item instanceof String text) {
                    result.add(text);
                }
            }
        }
        return result;
    }

    private Map<String, Object> env(Map<String, Object> data) {
        if (data.get("env") instanceof Map<?, ?> values) {
            Map<String, Object> result = new LinkedHashMap<>();
            values.forEach((key, value) -> result.put(String.valueOf(key), value));
            return result;
        }
        return new LinkedHashMap<>();
    }

    private String text(Object value) {
        return value == null ? "" : String.valueOf(value);
    }
}
