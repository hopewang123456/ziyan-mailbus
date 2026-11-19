-- 011 大屏登记：公开登记、心跳、离线判定与遥控目标。

CREATE TABLE IF NOT EXISTS collab_screens (
    screen_id    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    floor_id     TEXT,
    seat_id      TEXT,
    online       INTEGER NOT NULL DEFAULT 1,
    last_seen_at REAL,
    created_at   REAL NOT NULL
);
