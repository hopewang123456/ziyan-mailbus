-- 036 大屏密钥只保留哈希：secret 改名 secret_hash 并清空旧明文。
-- 旧明文不可逆推，现有屏幕需重新登记获取一次性明文密钥。

ALTER TABLE collab_screens RENAME COLUMN secret TO secret_hash;

UPDATE collab_screens SET secret_hash = NULL;
