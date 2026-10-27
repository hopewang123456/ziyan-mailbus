package io.github.hopewang123456.mailbus.ports;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 任务文件存取端口 — python {@code TaskTracker}（{data_dir}/tasks/{task_id}.json）
 * 的 java 镜像。M2a：与 python 共享同一份 JSON 任务文件（双栈同池），
 * Map 形状即 python 任务字典（宽松字段，未知键原样保留）。
 */
public interface TaskRepository {

    /** 单任务读取；不存在返回 empty。 */
    Optional<Map<String, Object>> find(String taskId);

    /** 原子写（tmp + rename，双栈并跑下避免半写文件）。 */
    void save(String taskId, Map<String, Object> task);

    /** 全量任务列表，按 created_at 升序（python list_all 语义）。 */
    List<Map<String, Object>> listAll();
}
