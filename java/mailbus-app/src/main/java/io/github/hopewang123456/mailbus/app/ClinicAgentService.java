package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 诊所与 agent 生命周期（java 机制深化批三，2026-10-30）— python 对等：
 * clinic tools 清单（形状对齐；run 显式 501——java 无 python 工具链）、
 * clinic jobs = 调度器状态（java TaskScanScheduler 同构）、
 * agents/active = 三级门禁（角色 enabled → 实例 enabled → 框架 registry enabled）。
 */
public class ClinicAgentService {

    private final Path dataDir;

    public ClinicAgentService(Path dataDir) {
        this.dataDir = dataDir;
    }

    // ── clinic tools（python CLINIC_TOOLS 清单形状；run 需 python 工具链，java 501）──

    /** python list_clinic_tools 清单（id/name/category/description/params/presets/script）。 */
    public List<Map<String, Object>> clinicTools() {
        List<Map<String, Object>> out = new ArrayList<>();
        for (String[] t : new String[][]{
                {"check-token-status", "Token 状态检查", "auth", "检查 API token 配置与鉴权可用性"},
                {"validate-scheduler", "调度器校验", "scheduler", "校验调度任务配置与上次执行状态"},
                {"diagnose-blockers", "阻塞诊断", "tasks", "扫描阻塞/失败任务并给出处置建议"},
                {"validate-agents-config", "Agent 配置校验", "agents", "校验 agents/框架/实例配置一致性"},
                {"resolve-agent-cli", "Agent CLI 解析", "agents", "解析 agent CLI 启动命令与可达性"},
                {"smoke-hermes-profiles", "Hermes 冒烟", "agents", "对 hermes_profile agent 发冒烟消息"},
                {"inbox-pending-dump", "收件箱积压导出", "inbox", "导出各 agent 未读积压明细"},
                {"fix-cline-auth", "Cline 鉴权修复", "auth", "修复 cline provider 鉴权配置"},
                {"mailbus-doctor-report", "Doctor 报告", "health", "运行结构化诊断并生成报告"},
                {"platform-probe", "平台探测", "health", "探测运行平台环境（docker/native）"},
        }) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", t[0]);
            item.put("name", t[1]);
            item.put("category", t[2]);
            item.put("description", t[3]);
            item.put("params", List.of());
            item.put("presets", List.of(Map.of("label", "run", "args", List.of())));
            item.put("script", "tools/clinic/" + t[0] + ".py");
            item.put("note", "java 面板只读清单；执行走 python 工具链（批三登记）");
            out.add(item);
        }
        return out;
    }

    // ── clinic jobs（python scheduler _hub_state 形状）──

    /** python get_scheduler_status：{running, started_at, jobs, last_error}。 */
    public Map<String, Object> schedulerStatus(boolean scanEnabled) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("running", scanEnabled);
        out.put("started_at", scanEnabled ? nowIso() : null);
        // jobs：从 scheduler-state.json 读上次状态（java TaskScanScheduler 同构落盘）
        Map<String, Object> state = JsonFiles.readMap(dataDir.resolve("scheduler-state.json"));
        out.put("jobs", state != null && state.get("jobs") instanceof Map<?, ?> jm ? jm : Map.of());
        out.put("last_error", state != null ? state.get("last_error") : null);
        out.put("tick_seconds", 30);
        out.put("note", "java 侧调度器=TaskScanScheduler（30s 兜底扫描），任务族较 python 精简（批三登记）");
        return out;
    }

    // ── agents/active（python list_active_agents 三级门禁直译）──

    /**
     * 三级门禁：角色 enabled（退役门）→ 实例 enabled（监测门）→ 框架 registry enabled。
     * 返回 {agentId: {type, framework, ...card 字段}}——python active_agents 同形。
     */
    public Map<String, Object> activeAgents() {
        Map<String, Object> cfg = readConfig();
        Map<String, Object> agents = cfg.get("agents") instanceof Map<?, ?> am ? cast(am) : Map.of();
        Map<String, Object> instances = cfg.get("agent_instances") instanceof Map<?, ?> im ? cast(im) : Map.of();
        Map<String, Object> frameworks = cfg.get("frameworks") instanceof Map<?, ?> fm ? cast(fm) : Map.of();
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map.Entry<String, Object> e : agents.entrySet()) {
            if (!(e.getValue() instanceof Map<?, ?> acRaw)) {
                continue;
            }
            Map<String, Object> ac = cast(acRaw);
            // 1) 角色级 enabled
            if (Boolean.FALSE.equals(ac.get("enabled"))) {
                continue;
            }
            // 2) 实例级 enabled
            String iid = str(ac.get("instance_id"));
            if (!iid.isEmpty() && instances.get(iid) instanceof Map<?, ?> inst
                    && Boolean.FALSE.equals(inst.get("enabled"))) {
                continue;
            }
            // 3) 框架 registry enabled
            String fw = !str(ac.get("type")).isEmpty() ? str(ac.get("type")) : str(ac.get("framework"));
            if (!fw.isEmpty() && frameworks.get(fw) instanceof Map<?, ?> fwr
                    && Boolean.FALSE.equals(fwr.get("enabled"))) {
                continue;
            }
            Map<String, Object> row = new LinkedHashMap<>(ac);
            row.put("type", fw);
            row.put("framework", fw);
            out.put(e.getKey(), row);
        }
        return out;
    }

    /** GET /api/agents/assembly — 装配视图骨架（python agent 装配 registry 机制，登记）。 */
    public Map<String, Object> agentsAssembly() {
        Map<String, Object> cfg = readConfig();
        Map<String, Object> agents = cfg.get("agents") instanceof Map<?, ?> am ? cast(am) : Map.of();
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map.Entry<String, Object> e : agents.entrySet()) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("agent", e.getKey());
            row.put("type", e.getValue() instanceof Map<?, ?> m ? str(((Map<?, ?>) m).get("type")) : "");
            row.put("note", "java 装配视图骨架（批三登记）");
            out.put(e.getKey(), row);
        }
        return out;
    }

    private Map<String, Object> readConfig() {
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        return cfg == null ? Map.of() : cfg;
    }

    private static String nowIso() {
        return OffsetDateTime.now(ZoneId.systemDefault())
                .format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssZ"));
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }
}
