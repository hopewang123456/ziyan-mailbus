package io.github.hopewang123456.mailbus.common;

import org.springframework.stereotype.Component;

import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.UUID;

@Component
public class Ids {

    private final SecureRandom random = new SecureRandom();

    public String next(String prefix) {
        return prefix + "_" + UUID.randomUUID().toString().replace("-", "");
    }

    public String token() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return "mb_" + HexFormat.of().formatHex(bytes);
    }
}
