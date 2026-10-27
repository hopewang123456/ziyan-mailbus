package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.app.ResultIngestService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 任务结果扫描兜底（M2b，python pipeline scan/watchdog 精神）：周期扫
 * executing 任务消化 msg-results。主路径是 step-result 端点的 G-02 立即
 * 推进，本 job 只兜「agent 直接写文件不走端点」的场景。
 * mailbus.task-scan.enabled=false 可关（测试/纯文件互操作场景）。
 */
@Component
@ConditionalOnProperty(name = "mailbus.task-scan.enabled", havingValue = "true", matchIfMissing = true)
public class TaskScanScheduler {

    private static final org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(TaskScanScheduler.class);

    private final ResultIngestService ingest;

    public TaskScanScheduler(ResultIngestService ingest) {
        this.ingest = ingest;
    }

    @Scheduled(fixedDelayString = "${mailbus.task-scan.interval-ms:30000}",
            initialDelayString = "${mailbus.task-scan.initial-delay-ms:15000}")
    public void scan() {
        try {
            var out = ingest.scanAll();
            int advanced = ((Number) out.getOrDefault("advanced", 0)).intValue();
            if (advanced > 0) {
                log.info("task scan advanced {} task(s): {}", advanced, out.get("actions"));
            }
        } catch (RuntimeException e) {
            log.warn("task scan failed: {}", String.valueOf(e.getMessage()));
        }
    }
}
