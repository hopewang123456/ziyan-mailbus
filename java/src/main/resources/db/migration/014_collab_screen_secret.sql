-- M14：大屏登记密钥，公开心跳/离线需校验，阻断匿名篡改归属与 DoS。
ALTER TABLE collab_screens ADD COLUMN secret TEXT;
