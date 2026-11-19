package io.github.hopewang123456.mailbus.common;

import org.springframework.http.HttpStatus;

public class ApiException extends RuntimeException {

    private final String code;
    private final String messageZh;
    private final HttpStatus status;

    public ApiException(String code, String messageZh, HttpStatus status) {
        super(messageZh);
        this.code = code;
        this.messageZh = messageZh;
        this.status = status;
    }

    public String code() {
        return code;
    }

    public String messageZh() {
        return messageZh;
    }

    public HttpStatus status() {
        return status;
    }

    public static ApiException notFound(String message) {
        return new ApiException("not_found", message, HttpStatus.NOT_FOUND);
    }

    public static ApiException notFound(String code, String message) {
        return new ApiException(code, message, HttpStatus.NOT_FOUND);
    }

    public static ApiException forbidden(String message) {
        return new ApiException("permission_denied", message, HttpStatus.FORBIDDEN);
    }

    public static ApiException unauthorized(String message) {
        return new ApiException("unauthorized", message, HttpStatus.UNAUTHORIZED);
    }

    /** Python 领域错误基类默认映射：400，保留业务 error_code。 */
    public static ApiException domain(String code, String message) {
        return new ApiException(code, message, HttpStatus.BAD_REQUEST);
    }

    /** 与 FastAPI RequestValidationError 一致：422 + validation_error。 */
    public static ApiException unprocessable() {
        return new ApiException("validation_error", "请求参数不合法",
                HttpStatus.UNPROCESSABLE_ENTITY);
    }

    public static ApiException conflict(String code, String message) {
        return new ApiException(code, message, HttpStatus.CONFLICT);
    }

    public static ApiException invalid(String message) {
        return new ApiException("invalid_state", message, HttpStatus.CONFLICT);
    }

    public static ApiException badRequest(String message) {
        return new ApiException("invalid_request", message, HttpStatus.BAD_REQUEST);
    }
}
