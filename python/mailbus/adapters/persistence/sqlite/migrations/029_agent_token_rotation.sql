-- 029 外壳 token 轮转：旧 token 保留 24h 宽限。
ALTER TABLE agents ADD COLUMN endpoint_token_prev TEXT;
ALTER TABLE agents ADD COLUMN endpoint_token_prev_expires_at REAL;

-- token 反查是热路径，必须唯一；SQLite 唯一索引允许多个 NULL。
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_endpoint_token
    ON agents (endpoint_token);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_endpoint_token_prev
    ON agents (endpoint_token_prev);
