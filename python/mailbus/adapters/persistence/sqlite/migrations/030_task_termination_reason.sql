-- 030 任务终止原因：no_matching_branch / auto_terminated / manual。
ALTER TABLE task_tasks ADD COLUMN termination_reason TEXT;

UPDATE task_tasks
SET termination_reason = 'manual'
WHERE state = 'cancelled' AND termination_reason IS NULL;
