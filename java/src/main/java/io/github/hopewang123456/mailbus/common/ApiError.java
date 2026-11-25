package io.github.hopewang123456.mailbus.common;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

public record ApiError(
        String error,
        @JsonProperty("error_code") String errorCode,
        @JsonProperty("message_zh") String messageZh,
        @JsonInclude(JsonInclude.Include.NON_NULL) List<Map<String, Object>> errors,
        @JsonInclude(JsonInclude.Include.NON_NULL) Integer revision
) {
    public static ApiError of(String code, String message) {
        return new ApiError(code, code, message, null, null);
    }

    public static ApiError of(ApiException exception) {
        return new ApiError(exception.code(), exception.code(), exception.messageZh(),
                exception.errors(), exception.revision());
    }
}
