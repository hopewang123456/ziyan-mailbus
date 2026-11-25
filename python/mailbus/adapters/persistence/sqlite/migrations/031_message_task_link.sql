-- 031 消息回链任务：消息触发与任务派发产生的消息可用 task_id 反查。
ALTER TABLE msg_messages ADD COLUMN task_id TEXT;

CREATE INDEX IF NOT EXISTS idx_msg_messages_task
    ON msg_messages (task_id);
