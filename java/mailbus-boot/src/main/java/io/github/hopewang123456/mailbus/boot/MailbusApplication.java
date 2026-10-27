package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.adapters.filestore.FileMessageStore;
import io.github.hopewang123456.mailbus.adapters.memory.InMemoryMessageRepository;
import io.github.hopewang123456.mailbus.adapters.migration.PythonStoreReader;
import io.github.hopewang123456.mailbus.adapters.sqlite.SqliteMessageRepository;
import io.github.hopewang123456.mailbus.app.ArchiveService;
import io.github.hopewang123456.mailbus.app.DemoService;
import io.github.hopewang123456.mailbus.app.MigrationService;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.ports.MessageArchiver;
import io.github.hopewang123456.mailbus.ports.StoreMigrator;
import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.ports.MessageRepository;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

import java.nio.file.Path;
import java.time.Clock;

/**
 * mailbus-j composition root — the ONLY module allowed to see every layer
 * (Python composition.py counterpart).
 *
 * Storage selection (plan §5): mailbus.storage = sqlite (default: Flyway
 * schema + file store) | memory (demo/tests). MySQL switch is datasource
 * config only (spring.datasource.*), same repository code.
 */
@SpringBootApplication(scanBasePackages = "io.github.hopewang123456.mailbus")
@org.springframework.scheduling.annotation.EnableScheduling
public class MailbusApplication {

    public static void main(String[] args) {
        ensureDataDir(args);
        SpringApplication.run(MailbusApplication.class, args);
    }

    /** mailbus init semantics: the data dir must exist before SQLite opens (mkdir -p). */
    private static void ensureDataDir(String[] args) {
        String dir = "./store";
        for (String a : args) {
            if (a.startsWith("--mailbus.data-dir=")) dir = a.substring("--mailbus.data-dir=".length());
        }
        try {
            java.nio.file.Files.createDirectories(java.nio.file.Path.of(dir));
        } catch (java.io.IOException e) {
            throw new IllegalStateException("cannot create data dir: " + dir, e);
        }
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC(); // domain discipline: UTC only
    }

    /** P2 指标（B1 双栈同源 manifest；D8：值计算在 app 层，Micrometer 注册在此）。 */
    @Bean
    io.github.hopewang123456.mailbus.app.MetricsManifestService metricsManifestService(
            org.springframework.core.env.Environment env) {
        return new io.github.hopewang123456.mailbus.app.MetricsManifestService(
                java.nio.file.Path.of(env.getProperty("mailbus.data-dir", "./store")),
                io.github.hopewang123456.mailbus.app.SharedRoots.resolve(env.getProperty("mailbus.root")));
    }

    @Bean
    io.github.hopewang123456.mailbus.app.MailbusMetricsCalculator mailbusMetricsCalculator(
            io.github.hopewang123456.mailbus.app.MetricsManifestService manifest,
            @org.springframework.beans.factory.annotation.Qualifier("messageRepository")
            io.github.hopewang123456.mailbus.ports.MessageRepository messages,
            io.github.hopewang123456.mailbus.ports.AgentDirectory agents) {
        return new io.github.hopewang123456.mailbus.app.MailbusMetricsCalculator(manifest, messages, agents);
    }

    /** P2 收尾：AI 助手（ChatClient 就位时装配；否则 controller 走 501） */
    @Bean
    io.github.hopewang123456.mailbus.app.DocsRagService docsRagService(
            org.springframework.core.env.Environment env) {
        // docs 知识库在仓库根（shared/ 的父级），与 python rag source（store 相对 ../docs）同源
        var sharedRoot = io.github.hopewang123456.mailbus.app.SharedRoots.resolve(env.getProperty("mailbus.root"));
        return new io.github.hopewang123456.mailbus.app.DocsRagService(sharedRoot.getParent());
    }

    @Bean
    AssistantService assistantService(
            org.springframework.beans.factory.ObjectProvider<org.springframework.ai.chat.model.ChatModel> chatModel,
            io.github.hopewang123456.mailbus.app.DocsRagService rag,
            io.github.hopewang123456.mailbus.app.MetricsManifestService manifest,
            io.github.hopewang123456.mailbus.app.MailbusMetricsCalculator calculator) {
        return new AssistantService(chatModel, rag, manifest, calculator);
    }

    @Bean
    MailbusMetricsBinder mailbusMetricsBinder(
            io.github.hopewang123456.mailbus.app.MetricsManifestService manifest,
            io.github.hopewang123456.mailbus.app.MailbusMetricsCalculator calculator) {
        return new MailbusMetricsBinder(manifest, calculator);
    }

    /** Files-as-SoT layer — always present; writes flow through the composite repo. */
    @Bean
    FileMessageStore fileMessageStore(org.springframework.core.env.Environment env) {
        return new FileMessageStore(Path.of(env.getProperty("mailbus.data-dir", "./store")));
    }

    @Bean
    @ConditionalOnProperty(name = "mailbus.storage", havingValue = "sqlite", matchIfMissing = true)
    MessageRepository sqliteIndex(org.springframework.jdbc.core.JdbcTemplate jdbc) {
        return new SqliteMessageRepository(jdbc);
    }

    @Bean
    @ConditionalOnProperty(name = "mailbus.storage", havingValue = "memory")
    MessageRepository memoryIndex() {
        return new InMemoryMessageRepository();
    }

    /** Composite: file write first, index second — a crash leaves unindexed files
     *  (recoverable by rescan), never a dangling index row. */
    @Bean
    MessageRepository messageRepository(FileMessageStore files,
                                        @org.springframework.beans.factory.annotation.Qualifier("sqliteIndex")
                                        ObjectProvider<MessageRepository> sqlite,
                                        @org.springframework.beans.factory.annotation.Qualifier("memoryIndex")
                                        ObjectProvider<MessageRepository> memory) {
        MessageRepository index = sqlite.getIfAvailable() != null
                ? sqlite.getIfAvailable()
                : memory.getIfAvailable();
        if (index == null) {
            throw new IllegalStateException("no storage index bean matched (mailbus.storage=?)");
        }
        return new FileMessageStore.FileIndexedMessages(files, index);
    }

    @Bean
    io.github.hopewang123456.mailbus.ports.AgentDirectory agentDirectory(
            org.springframework.jdbc.core.JdbcTemplate jdbc, Clock clock) {
        return new io.github.hopewang123456.mailbus.adapters.frameworks.CliAgentDirectory(jdbc, clock);
    }

    @Bean
    io.github.hopewang123456.mailbus.app.PushService pushService(
            @org.springframework.beans.factory.annotation.Qualifier("messageRepository")
            io.github.hopewang123456.mailbus.ports.MessageRepository repo,
            io.github.hopewang123456.mailbus.ports.AgentDirectory directory,
            io.github.hopewang123456.mailbus.ports.MessageEventLog events) {
        return new io.github.hopewang123456.mailbus.app.PushService(repo, directory, events);
    }

    @Bean
    io.github.hopewang123456.mailbus.app.PushService.Cards agentCards(
            io.github.hopewang123456.mailbus.ports.AgentDirectory directory) {
        return new io.github.hopewang123456.mailbus.app.PushService.Cards(directory);
    }

    @Bean
    io.github.hopewang123456.mailbus.ports.AgentCardImporter.Factory agentCardImporterFactory() {
        return new io.github.hopewang123456.mailbus.adapters.frameworks.TransportCardImporter.Factory();
    }

    @Bean
    io.github.hopewang123456.mailbus.app.ReconcileService reconcileService(
            @org.springframework.beans.factory.annotation.Qualifier("messageRepository")
            io.github.hopewang123456.mailbus.ports.MessageRepository repo) {
        return new io.github.hopewang123456.mailbus.app.ReconcileService(repo);
    }

    @Bean
    io.github.hopewang123456.mailbus.ports.MessageEventLog messageEventLog(
            org.springframework.jdbc.core.JdbcTemplate jdbc, Clock clock) {
        return new io.github.hopewang123456.mailbus.adapters.sqlite.SqliteEventLog(jdbc, clock);
    }

    @Bean
    io.github.hopewang123456.mailbus.ports.Notifier notifier(FileMessageStore files,
            org.springframework.core.env.Environment env, Clock clock) {
        String webhook = env.getProperty("mailbus.notify.webhook-url", "");
        var smtp = new io.github.hopewang123456.mailbus.adapters.notify.SmtpNotifier(
                env.getProperty("mailbus.notify.smtp.host", ""),
                env.getProperty("mailbus.notify.smtp.port", Integer.class, 465),
                env.getProperty("mailbus.notify.smtp.from", ""),
                env.getProperty("mailbus.notify.smtp.to", ""),
                env.getProperty("mailbus.notify.smtp.username", ""),
                env.getProperty("mailbus.notify.smtp.password", ""),
                env.getProperty("mailbus.notify.smtp.starttls", Boolean.class, false));
        io.github.hopewang123456.mailbus.ports.Notifier desktop =
                new io.github.hopewang123456.mailbus.adapters.notify.DesktopNotifier();
        var channels = new java.util.ArrayList<io.github.hopewang123456.mailbus.ports.Notifier>();
        channels.add(new io.github.hopewang123456.mailbus.adapters.notify.WebhookNotifier(webhook, clock));
        channels.add(new io.github.hopewang123456.mailbus.adapters.notify.FileDigestNotifier(files.root(), clock));
        channels.add(desktop);
        if (smtp.enabled()) {
            channels.add(smtp);
        }
        return io.github.hopewang123456.mailbus.ports.Notifier.fanOut(
                channels.toArray(new io.github.hopewang123456.mailbus.ports.Notifier[0]));
    }

    @Bean
    io.github.hopewang123456.mailbus.app.PatrolService patrolService(
            @org.springframework.beans.factory.annotation.Qualifier("messageRepository")
            io.github.hopewang123456.mailbus.ports.MessageRepository repo,
            io.github.hopewang123456.mailbus.ports.MessageEventLog events,
            io.github.hopewang123456.mailbus.ports.Notifier notifier) {
        return new io.github.hopewang123456.mailbus.app.PatrolService(repo, events, notifier);
    }

    @Bean
    io.github.hopewang123456.mailbus.app.StatusService statusService(
            @org.springframework.beans.factory.annotation.Qualifier("messageRepository")
            io.github.hopewang123456.mailbus.ports.MessageRepository repo) {
        return new io.github.hopewang123456.mailbus.app.StatusService(repo);
    }

    @Bean
    io.github.hopewang123456.mailbus.app.AcceptanceService acceptanceService(
            @org.springframework.beans.factory.annotation.Qualifier("messageRepository")
            io.github.hopewang123456.mailbus.ports.MessageRepository repo,
            io.github.hopewang123456.mailbus.ports.MessageEventLog events) {
        return new io.github.hopewang123456.mailbus.app.AcceptanceService(repo, events);
    }

    @Bean
    StoreMigrator.Factory storeMigratorFactory() {
        return new PythonStoreReader.Factory();
    }

    @Bean
    MigrationService.ShardWriter shardWriter(FileMessageStore files) {
        return record -> java.nio.file.Files.isRegularFile(files.shardPath(record));
    }

    @Bean
    MigrationService migrationService(@org.springframework.beans.factory.annotation.Qualifier("messageRepository")
                                      MessageRepository repo, FileMessageStore files, Clock clock) {
        return new MigrationService(repo, files.root(), clock);
    }

    @Bean
    ArchiveService archiveService(@org.springframework.beans.factory.annotation.Qualifier("messageRepository")
                                  MessageRepository repo, FileMessageStore files,
                                  io.github.hopewang123456.mailbus.ports.MessageEventLog events) {
        return new ArchiveService(repo, files, events);
    }

    @Bean
    DemoService demoService(InboxService inbox, ArchiveService archive) {
        return new DemoService(inbox, archive);
    }

    @Bean
    InboxService inboxService(@org.springframework.beans.factory.annotation.Qualifier("messageRepository")
                               MessageRepository messages,
                               io.github.hopewang123456.mailbus.ports.MessageEventLog events,
                               Clock clock) {
        return new InboxService(messages, events, clock);
    }

    // ── M2a 任务引擎（python tasks/*.json 共享任务池，M2-S1）────────────────

    private static java.nio.file.Path dataDir(org.springframework.core.env.Environment env) {
        return io.github.hopewang123456.mailbus.app.SharedRoots
                .resolveDataDir(env.getProperty("mailbus.data-dir"));
    }

    @Bean
    io.github.hopewang123456.mailbus.ports.TaskRepository taskRepository(
            org.springframework.core.env.Environment env) {
        return new io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository(dataDir(env));
    }

    @Bean
    io.github.hopewang123456.mailbus.app.RoleResolverService roleResolverService(
            org.springframework.core.env.Environment env,
            io.github.hopewang123456.mailbus.ports.TaskRepository tasks) {
        return new io.github.hopewang123456.mailbus.app.RoleResolverService(dataDir(env), tasks);
    }

    /** M2b：结果消化引擎（G-02 立即推进 + scan 兜底的共享内核）。 */
    @Bean
    io.github.hopewang123456.mailbus.app.ResultIngestService resultIngestService(
            org.springframework.core.env.Environment env,
            io.github.hopewang123456.mailbus.ports.TaskRepository tasks,
            io.github.hopewang123456.mailbus.app.RoleResolverService resolver,
            Clock clock) {
        var dir = dataDir(env);
        return new io.github.hopewang123456.mailbus.app.ResultIngestService(
                dir, clock, tasks, resolver,
                new io.github.hopewang123456.mailbus.app.HumanQueueService(dir, clock));
    }

    @Bean
    io.github.hopewang123456.mailbus.app.TaskService taskService(
            org.springframework.core.env.Environment env,
            io.github.hopewang123456.mailbus.ports.TaskRepository tasks,
            io.github.hopewang123456.mailbus.app.RoleResolverService resolver,
            io.github.hopewang123456.mailbus.app.TaskPlannerService planner,
            Clock clock) {
        var dir = dataDir(env);
        var svc = new io.github.hopewang123456.mailbus.app.TaskService(
                dir, clock, tasks, resolver,
                new io.github.hopewang123456.mailbus.app.HumanQueueService(dir, clock));
        svc.setPlanner(planner); // M2c：解锁 auto 模式（tier0 规则 + 可选 LLM）
        return svc;
    }

    // ── M2c 发令聚合：planner（tier0 + 可选 Spring AI）+ draft/inbox ──────────

    /** LLM 回调：ChatModel 就绪时经 Spring AI ChatClient 补全（ObjectProvider 判空，勿用 @ConditionalOnBean）。 */
    @Bean
    io.github.hopewang123456.mailbus.app.TaskPlannerService taskPlannerService(
            org.springframework.core.env.Environment env,
            org.springframework.beans.factory.ObjectProvider<org.springframework.ai.chat.model.ChatModel> chatModel) {
        var cm = chatModel.getIfAvailable();
        io.github.hopewang123456.mailbus.app.TaskPlannerService.LlmClient llm = null;
        if (cm != null) {
            llm = (system, user) -> {
                try {
                    return org.springframework.ai.chat.client.ChatClient.builder(cm).build()
                            .prompt().system(system).user(user).call().content();
                } catch (RuntimeException e) {
                    throw new io.github.hopewang123456.mailbus.app.TaskPlannerService.LlmError(
                            String.valueOf(e.getMessage()));
                }
            };
        }
        return new io.github.hopewang123456.mailbus.app.TaskPlannerService(dataDir(env), llm);
    }

    @Bean
    io.github.hopewang123456.mailbus.app.CommandDraftService commandDraftService(
            io.github.hopewang123456.mailbus.app.TaskPlannerService planner) {
        return new io.github.hopewang123456.mailbus.app.CommandDraftService(planner);
    }

    @Bean
    io.github.hopewang123456.mailbus.app.CommandInboxService commandInboxService(
            org.springframework.core.env.Environment env,
            io.github.hopewang123456.mailbus.ports.TaskRepository tasks,
            Clock clock) {
        var dir = dataDir(env);
        return new io.github.hopewang123456.mailbus.app.CommandInboxService(
                dir, tasks, new io.github.hopewang123456.mailbus.app.HumanQueueService(dir, clock));
    }

    /** M2d-a：A2A 入站代理（JSON-RPC SendMessage/GetTask/CancelTask，python handlers_a2a 对等）。 */
    @Bean
    io.github.hopewang123456.mailbus.app.A2aRpcService a2aRpcService(
            org.springframework.core.env.Environment env,
            io.github.hopewang123456.mailbus.app.TaskService tasks,
            io.github.hopewang123456.mailbus.ports.TaskRepository repo,
            Clock clock) {
        var dir = dataDir(env);
        return new io.github.hopewang123456.mailbus.app.A2aRpcService(
                dir, tasks, repo,
                new io.github.hopewang123456.mailbus.app.HumanQueueService(dir, clock));
    }

    /** 交接③：工作流模板 registry CRUD（python handlers_workflows 对等，SoT 双栈共享）。 */
    @Bean
    io.github.hopewang123456.mailbus.app.WorkflowsService workflowsService(
            org.springframework.core.env.Environment env, Clock clock) {
        return new io.github.hopewang123456.mailbus.app.WorkflowsService(dataDir(env), clock);
    }

    /** M2a 起 positions 候选池 busy/active 为任务池真值（原 controller 自建改 boot 装配）。 */
    @Bean
    io.github.hopewang123456.mailbus.app.PositionCatalogService positionCatalogService(
            org.springframework.core.env.Environment env,
            io.github.hopewang123456.mailbus.app.RoleResolverService resolver) {
        return new io.github.hopewang123456.mailbus.app.PositionCatalogService(dataDir(env), resolver);
    }
}
