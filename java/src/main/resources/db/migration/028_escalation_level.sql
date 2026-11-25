-- 028 升级级别：1 一级 / 2 二级（二级无人处理自动终止）。
ALTER TABLE task_escalations ADD COLUMN level INTEGER NOT NULL DEFAULT 1;
