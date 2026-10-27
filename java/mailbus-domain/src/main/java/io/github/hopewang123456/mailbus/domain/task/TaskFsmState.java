package io.github.hopewang123456.mailbus.domain.task;

/**
 * 任务级 FSM 状态 — python {@code lib/domain/fsm.py TaskFsmState} 的镜像
 * （M2a，值必须与 python 完全一致：任务 JSON 双栈共享）。
 */
public enum TaskFsmState {
    CREATED("created"),
    EXECUTING("executing"),
    ACCEPTING("accepting"),   // 链完成，等待人工终验
    BLOCKED("blocked"),       // 步骤 fail 等待人工决策
    PAUSED("paused"),
    SUCCEEDED("succeeded"),
    FAILED("failed"),
    CANCELLED("cancelled");

    private final String value;

    TaskFsmState(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }

    /** 宽松解析：未知值返回 null（读 python 写的任务文件时保持原样）。 */
    public static TaskFsmState fromValue(String v) {
        for (TaskFsmState s : values()) {
            if (s.value.equals(v)) {
                return s;
            }
        }
        return null;
    }
}
