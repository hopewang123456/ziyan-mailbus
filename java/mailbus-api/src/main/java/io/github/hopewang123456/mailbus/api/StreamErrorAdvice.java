package io.github.hopewang123456.mailbus.api;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

/**
 * 流端点错误映射（PY4-A）— 并发流超限 → 503。
 *
 * <p>body 形状与 python 侧 {@code _send_api_error("too_many_streams", 503, …)}
 * 对齐：{@code {"status":"error","error":…,"message":…}}。
 */
@RestControllerAdvice(assignableTypes = StreamController.class)
public class StreamErrorAdvice {

    @ExceptionHandler(StreamController.StreamLimitException.class)
    public ResponseEntity<Map<String, Object>> onStreamLimit(StreamController.StreamLimitException e) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(Map.of(
                "status", "error",
                "error", "too_many_streams",
                "message", e.getMessage()));
    }
}
