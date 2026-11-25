package io.github.hopewang123456.mailbus.common;

import org.springframework.http.HttpStatus;

import java.util.List;
import java.util.Map;

public class ApiException extends RuntimeException {

    private final String code;
    private final String messageZh;
    private final HttpStatus status;
    private final List<Map<String, Object>> errors;
    private final Integer revision;

    public ApiException(String code, String messageZh, HttpStatus status) {
        this(code, messageZh, status, null, null);
    }

    public ApiException(String code, String messageZh, HttpStatus status,
                        List<Map<String, Object>> errors, Integer revision) {
        super(messageZh);
        this.code = code;
        this.messageZh = messageZh;
        this.status = status;
        this.errors = errors;
        this.revision = revision;
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

    public List<Map<String, Object>> errors() {
        return errors;
    }

    public Integer revision() {
        return revision;
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

    /** 资源已撤销或已过期：410。 */
    public static ApiException gone(String code, String message) {
        return new ApiException(code, message, HttpStatus.GONE);
    }

    /** 请求语义不成立（如 Agent 员工缺少岗位）：422 + 契约码。 */
    public static ApiException unprocessable(String code, String message) {
        return new ApiException(code, message, HttpStatus.UNPROCESSABLE_ENTITY);
    }

    /** 调用过于频繁：429。 */
    public static ApiException rateLimited(String message) {
        return new ApiException("rate_limited", message, HttpStatus.TOO_MANY_REQUESTS);
    }

    /** 容量已满（如公开大屏/长连接上限）：503。 */
    public static ApiException capacityExceeded(String message) {
        return new ApiException("capacity_exceeded", message,
                HttpStatus.SERVICE_UNAVAILABLE);
    }

    /** Graph 结构不合法：400，响应体附带可定位 issues。 */
    public static ApiException invalidGraph(String message, List<Map<String, Object>> errors) {
        return new ApiException("invalid_graph", message, HttpStatus.BAD_REQUEST, errors, null);
    }

    /** 乐观锁冲突：409，响应体附带服务端 revision。 */
    public static ApiException revisionConflict(String message, int revision) {
        return new ApiException("revision_conflict", message, HttpStatus.CONFLICT, null,
                revision);
    }

    /** 发布前强制校验失败：422，响应体附带 errors 清单。 */
    public static ApiException publishRejected(String message,
                                               List<Map<String, Object>> errors) {
        return new ApiException("publish_invalid", message,
                HttpStatus.UNPROCESSABLE_ENTITY, errors, null);
    }
}
