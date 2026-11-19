-- 012 结对与协同消息：pair 独立表；消息表补 pair 维度后复用现有消息投影。

CREATE TABLE IF NOT EXISTS collab_pairs (
    pair_id      TEXT PRIMARY KEY,
    initiator_id TEXT NOT NULL,
    partner_id   TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'active',
    created_at   REAL NOT NULL,
    ended_at     REAL
);

CREATE INDEX IF NOT EXISTS idx_collab_pairs_state
    ON collab_pairs (state, created_at);

ALTER TABLE msg_messages ADD COLUMN pair_id TEXT;

CREATE INDEX IF NOT EXISTS idx_msg_messages_pair
    ON msg_messages (pair_id, created_at);
