-- V2: content snapshot column.
-- Files remain the source of truth; content here is a write-time snapshot so
-- list queries avoid file IO (reconcile pass in M2 re-syncs hand-edited files).

ALTER TABLE msg_index ADD COLUMN content TEXT NOT NULL DEFAULT '';
