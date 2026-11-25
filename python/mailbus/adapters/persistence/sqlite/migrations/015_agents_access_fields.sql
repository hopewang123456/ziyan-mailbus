-- 015 agents 接入字段：外壳类型、通道类型、端点 token、最后在线时间。
-- 现有 6 个 hermes_profile 明确走 A2A；其余未绑定外壳保持默认值，接入时再按实际方式更新。
ALTER TABLE agents ADD COLUMN agent_type TEXT NOT NULL DEFAULT 'service';
ALTER TABLE agents ADD COLUMN channel_type TEXT NOT NULL DEFAULT 'a2a';
ALTER TABLE agents ADD COLUMN endpoint_token TEXT;
ALTER TABLE agents ADD COLUMN last_seen_at REAL;

UPDATE agents SET channel_type = 'a2a' WHERE framework = 'hermes_profile';
