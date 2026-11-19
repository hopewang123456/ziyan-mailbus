package io.github.hopewang123456.mailbus.common;

import com.fasterxml.jackson.annotation.JsonProperty;

public record ApiError(
        String error,
        @JsonProperty("error_code") String errorCode,
        @JsonProperty("message_zh") String messageZh
) {
    public static ApiError of(String code, String message) {
        return new ApiError(code, code, message);
    }
}
