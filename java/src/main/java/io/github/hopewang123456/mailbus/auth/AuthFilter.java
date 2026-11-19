package io.github.hopewang123456.mailbus.auth;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.common.ApiError;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
public class AuthFilter extends OncePerRequestFilter {

    public static final String ACTOR_ATTRIBUTE = "mailbus.actor";
    private static final String BEARER = "Bearer ";

    private final TokenResolver tokens;
    private final ObjectMapper objectMapper;

    public AuthFilter(TokenResolver tokens, ObjectMapper objectMapper) {
        this.tokens = tokens;
        this.objectMapper = objectMapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        String method = request.getMethod();
        if ("OPTIONS".equalsIgnoreCase(method)) {
            return true;
        }
        if (path.equals("/api/health") || path.equals("/api/openapi.json")
                || path.equals("/error") || path.equals("/api/public/layout")
                || path.startsWith("/api/public/collab/")) {
            return true;
        }
        if (path.equals("/api/identity/bootstrap") && "GET".equals(method)) {
            return true;
        }
        if (path.equals("/api/identity/bootstrap/super-admin") && "POST".equals(method)) {
            return true;
        }
        return path.equals("/api/identity/staff") && "POST".equals(method);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith(BEARER)) {
            writeUnauthorized(response, "缺少 Bearer 凭证");
            return;
        }
        String token = header.substring(BEARER.length()).trim();
        if (token.isEmpty()) {
            writeUnauthorized(response, "缺少 Bearer 凭证");
            return;
        }
        Actor actor = tokens.resolve(token);
        if (actor == null) {
            writeUnauthorized(response, "登录凭证无效或已过期");
            return;
        }
        request.setAttribute(ACTOR_ATTRIBUTE, actor);
        filterChain.doFilter(request, response);
    }

    private void writeUnauthorized(HttpServletResponse response, String message) throws IOException {
        response.setStatus(HttpStatus.UNAUTHORIZED.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(response.getWriter(),
                ApiError.of("unauthorized", message));
    }
}
