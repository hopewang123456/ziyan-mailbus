package io.github.hopewang123456.mailbus.integrations;

import java.util.List;
import java.util.Map;

public final class IntegrationDtos {

    private IntegrationDtos() {
    }

    public record IntegrationItemOut(String name, String kind, String description,
                                     List<String> actions) {
    }

    public record IntegrationsOut(List<IntegrationItemOut> integrations,
                                  List<String> plugins, String note) {
    }

    public record PluginActionIn(String action, String spec) {
    }

    public record PluginActionOut(List<String> plugins) {
    }

    public record IntegrationInvokeIn(String action, Map<String, Object> params) {
        public IntegrationInvokeIn {
            if (params == null) {
                params = Map.of();
            }
        }
    }

    public record IntegrationInvokeOut(String name, String action,
                                       Map<String, Object> result) {
    }

    public record EnvEntryOut(String key, String label, String value, boolean configured) {
    }

    public record EnvGroupsOut(Map<String, List<EnvEntryOut>> groups) {
    }

    public record EnvUpdateIn(Map<String, String> vars) {
        public EnvUpdateIn {
            if (vars == null) {
                vars = Map.of();
            }
        }
    }

    public record ReloadOut(boolean reloaded, List<String> plugins) {
    }
}
