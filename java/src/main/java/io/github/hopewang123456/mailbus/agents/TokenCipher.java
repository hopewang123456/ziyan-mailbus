package io.github.hopewang123456.mailbus.agents;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;

/** 与 Python 互通的 AES-GCM token 加密 + HMAC 反查摘要。 */
@Component
public class TokenCipher {

    private static final String PREFIX = "enc:";
    private static final byte[] AAD = "mailbus-agent-token".getBytes(StandardCharsets.UTF_8);
    private static final int NONCE_BYTES = 12;

    private final byte[] key;
    private final byte[] lookupKey;
    private final SecureRandom random = new SecureRandom();

    public TokenCipher(@Value("${mailbus.token-encryption-key:}") String material) {
        String secret = material == null ? "" : material.strip();
        if (secret.isEmpty()) {
            throw new IllegalStateException("缺少 MAILBUS_TOKEN_ENCRYPTION_KEY，无法处理 Agent token");
        }
        this.key = sha256(secret.getBytes(StandardCharsets.UTF_8));
        this.lookupKey = sha256(concat(key, ":lookup".getBytes(StandardCharsets.UTF_8)));
    }

    public String encrypt(String plaintext) {
        try {
            byte[] nonce = new byte[NONCE_BYTES];
            random.nextBytes(nonce);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"),
                    new GCMParameterSpec(128, nonce));
            cipher.updateAAD(AAD);
            byte[] body = cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8));
            return PREFIX + Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(concat(nonce, body));
        } catch (Exception exception) {
            throw new IllegalStateException("Agent token 加密失败", exception);
        }
    }

    public String decrypt(String ciphertext) {
        if (ciphertext == null || ciphertext.isBlank()) {
            return null;
        }
        try {
            String value = ciphertext.startsWith(PREFIX)
                    ? ciphertext.substring(PREFIX.length()) : ciphertext;
            byte[] raw = Base64.getUrlDecoder().decode(value);
            byte[] nonce = java.util.Arrays.copyOfRange(raw, 0, NONCE_BYTES);
            byte[] body = java.util.Arrays.copyOfRange(raw, NONCE_BYTES, raw.length);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"),
                    new GCMParameterSpec(128, nonce));
            cipher.updateAAD(AAD);
            return new String(cipher.doFinal(body), StandardCharsets.UTF_8);
        } catch (Exception exception) {
            return null;
        }
    }

    public String lookupDigest(String plaintext) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(lookupKey, "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(plaintext.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException("Agent token 摘要失败", exception);
        }
    }

    public String fingerprint(String plaintext) {
        return HexFormat.of().formatHex(sha256(plaintext.getBytes(StandardCharsets.UTF_8)))
                .substring(0, 12);
    }

    private static byte[] sha256(byte[] value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value);
        } catch (Exception exception) {
            throw new IllegalStateException("SHA-256 不可用", exception);
        }
    }

    private static byte[] concat(byte[] left, byte[] right) {
        byte[] merged = java.util.Arrays.copyOf(left, left.length + right.length);
        System.arraycopy(right, 0, merged, left.length, right.length);
        return merged;
    }
}
