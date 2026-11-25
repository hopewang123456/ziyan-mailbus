-- 026 任务循环计数（JSON: {node_id: times}），用于循环保护。
ALTER TABLE task_tasks ADD COLUMN loop_counters TEXT NOT NULL DEFAULT '{}';
