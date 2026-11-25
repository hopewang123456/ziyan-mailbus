-- 016 员工待办计数：调度按 pending 最少优先，避免每次聚合 task_node_runs。
ALTER TABLE identity_employees ADD COLUMN pending_task_count INTEGER NOT NULL DEFAULT 0;
