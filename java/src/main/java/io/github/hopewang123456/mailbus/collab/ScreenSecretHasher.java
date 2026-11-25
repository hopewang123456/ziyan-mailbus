package io.github.hopewang123456.mailbus.collab;

import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/** 大屏密钥摘要：SHA-256 十六进制，常量时间比对。 */
@Component
public class ScreenSecretHasher {

    public String digest(String secret) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(secret.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder(bytes.length * 2);
            for (byte value : bytes) {
                hex.append(String.format("%02x", value));
            }
            return hex.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 不可用", exception);
        }
    }

    public boolean verify(String stored, String secret) {
        if (stored == null || secret == null || stored.isBlank() || secret.isBlank()) {
            return false;
        }
        return MessageDigest.isEqual(stored.getBytes(StandardCharsets.UTF_8),
                digest(secret).getBytes(StandardCharsets.UTF_8));
    }
}
