package io.github.hopewang123456.mailbus.domain.task;

import java.util.Set;

/**
 * 步骤级 FSM 状态 — python {@code lib/domain/fsm.py StepFsmState} 的镜像
 * （M2a，值必须与 python 完全一致）。
 */
public enum StepFsmState {
    PENDING("pending"),          // 尚未轮到
    QUEUED("queued"),            // 等待 dispatch
    DISPATCHED("dispatched"),    // 消息已写入 inbox
    IN_PROGRESS("in_progress"),  // agent 已 ack / CLI 活跃
    AWAITING_RESULT("awaiting_result"), // 等待 msg-results
    COMPLETED("completed"),
    FAILED("failed"),
    SKIPPED("skipped"),
    SUPERSEDED("superseded");    // 被回退覆盖

    /** 终态集合（active_step 判定与负载统计共用）。 */
    public static final Set<String> TERMINAL =
            Set.of(COMPLETED.value, FAILED.value, SKIPPED.value, SUPERSEDED.value);

    private final String value;

    StepFsmState(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
