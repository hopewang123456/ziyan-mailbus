package io.github.hopewang123456.mailbus.scheduler;

import io.github.hopewang123456.mailbus.config.AppProperties;
import io.github.hopewang123456.mailbus.dispatch.FileBusIngress;
import io.github.hopewang123456.mailbus.dispatch.OutboxDispatcher;
import io.github.hopewang123456.mailbus.identity.IdentityService;
import io.github.hopewang123456.mailbus.ops.OpsService;
import io.github.hopewang123456.mailbus.workflow.TaskService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Instant;

/** 后台巡检：心跳超时、审批超时、outbox 派发与 file_bus 入站。 */
@Component
public class MailbusScheduler {

    private static final Logger log = LoggerFactory.getLogger(MailbusScheduler.class);

    private final AppProperties properties;
    private final IdentityService identity;
    private final TaskService tasks;
    private final OutboxDispatcher dispatcher;
    private final FileBusIngress ingress;
    private final OpsService ops;

    public MailbusScheduler(AppProperties properties, IdentityService identity,
                            TaskService tasks, OutboxDispatcher dispatcher,
                            FileBusIngress ingress, OpsService ops) {
        this.properties = properties;
        this.identity = identity;
        this.tasks = tasks;
        this.dispatcher = dispatcher;
        this.ingress = ingress;
        this.ops = ops;
    }

    @Scheduled(fixedDelayString = "${mailbus.heartbeat-sweep-seconds}000")
    public void heartbeatSweep() {
        try {
            long cutoff = Instant.now().getEpochSecond()
                    - properties.heartbeatTimeoutSeconds();
            identity.markStaleOffline(cutoff);
        } catch (Exception exception) {
            log.warn("心跳巡检失败", exception);
        }
    }

    @Scheduled(fixedDelayString = "${mailbus.dispatch-interval-seconds}000")
    public void dispatch() {
        try {
            ops.evaluate();
        } catch (Exception exception) {
            log.warn("告警规则巡检失败", exception);
        }
        try {
            tasks.sweepTimeouts();
        } catch (Exception exception) {
            log.warn("任务与审批超时扫描失败", exception);
        }
        try {
            dispatcher.tick();
        } catch (Exception exception) {
            log.warn("outbox 派发失败", exception);
        }
        try {
            ingress.pollOnce();
        } catch (Exception exception) {
            log.warn("file_bus 入站扫描失败", exception);
        }
    }
}
