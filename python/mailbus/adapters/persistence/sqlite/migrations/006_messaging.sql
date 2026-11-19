-- 006 消息与投递：消息写入与 outbox 同事务，投递结果记入尝试表。

CREATE TABLE IF NOT EXISTS msg_messages (
    message_id   TEXT PRIMARY KEY,
    sender_id    TEXT NOT NULL,
    recipient_id TEXT,
    kind         TEXT NOT NULL DEFAULT 'note',
    body         TEXT NOT NULL,
    created_at   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_msg_messages_inbox
    ON msg_messages (recipient_id, created_at);

CREATE TABLE IF NOT EXISTS msg_delivery_attempts (
    message_id TEXT NOT NULL REFERENCES msg_messages (message_id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL,
    ok         INTEGER NOT NULL,
    error_code TEXT,
    detail     TEXT,
    at         REAL NOT NULL,
    PRIMARY KEY (message_id, attempt_no)
);
