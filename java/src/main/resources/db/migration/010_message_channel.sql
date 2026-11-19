-- 010 消息通道归档：a2a / mcp / file_bus 共用消息表，仅补通道列。

ALTER TABLE msg_messages ADD COLUMN channel TEXT NOT NULL DEFAULT 'file_bus';

CREATE INDEX IF NOT EXISTS idx_msg_messages_channel
    ON msg_messages (channel, created_at);
