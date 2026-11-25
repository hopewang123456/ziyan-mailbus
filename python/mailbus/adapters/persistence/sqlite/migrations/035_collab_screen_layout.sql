-- 035 大屏布局配置：草稿与已发布配置、来源标记、版本号与心跳索引。
-- 配置 JSON 字段：layout_type / theme / resolution / team_id / play_state / office / grid / custom。
-- 旧列 floor_id / seat_id 保留不删，旧屏幕统一接管为 manual，避免被自动清理。

ALTER TABLE collab_screens ADD COLUMN source TEXT NOT NULL DEFAULT 'auto';
ALTER TABLE collab_screens ADD COLUMN config_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE collab_screens ADD COLUMN published_config_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE collab_screens ADD COLUMN config_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE collab_screens ADD COLUMN updated_at REAL;

-- 旧屏幕回填：优先用原楼层/工位生成最小 office 布局作为初始聚焦，无法解析时保留空布局。
UPDATE collab_screens
SET source = 'manual',
    updated_at = COALESCE(last_seen_at, created_at),
    config_json = CASE
        WHEN floor_id IS NULL AND seat_id IS NULL THEN '{}'
        ELSE json_object(
            'layout_type', 'office',
            'theme', 'auto',
            'resolution', '1920x1080',
            'play_state', 'playing',
            'office', json_object('floor_id', floor_id, 'seat_id', seat_id)
        )
    END;

UPDATE collab_screens
SET published_config_json = config_json
WHERE source = 'manual' AND published_config_json = '{}';

-- 离线判定与自动登记清理。
CREATE INDEX IF NOT EXISTS idx_collab_screens_last_seen
    ON collab_screens (last_seen_at);
CREATE INDEX IF NOT EXISTS idx_collab_screens_source_seen
    ON collab_screens (source, last_seen_at);
