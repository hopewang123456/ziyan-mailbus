package io.github.hopewang123456.mailbus.agents;

import io.github.hopewang123456.mailbus.common.ApiException;

import java.net.InetAddress;
import java.net.URI;
import java.util.Set;

/** 出站 endpoint 的 SSRF 防护：仅 http(s)，阻断云元数据与受限地址。 */
public final class EndpointGuard {

    private static final Set<String> METADATA_HOSTS = Set.of(
            "metadata", "metadata.google.internal", "metadata.goog",
            "instance-data", "instance-data.ec2.internal");
    private static final Set<String> METADATA_IPS = Set.of(
            "169.254.169.254", "169.254.170.2", "100.100.100.200", "fd00:ec2::254");

    private EndpointGuard() {
    }

    public static String validate(String endpoint) {
        String text = endpoint == null ? "" : endpoint.strip();
        if (text.isEmpty()) {
            throw ApiException.unprocessable();
        }
        URI uri;
        try {
            uri = URI.create(text);
        } catch (IllegalArgumentException exception) {
            throw ApiException.unprocessable();
        }
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
        if (!"http".equals(scheme) && !"https".equals(scheme)) {
            throw ApiException.unprocessable();
        }
        if (uri.getHost() == null || uri.getHost().isBlank()) {
            throw ApiException.unprocessable();
        }
        if (uri.getUserInfo() != null) {
            throw ApiException.unprocessable();
        }
        String host = uri.getHost().toLowerCase().replaceAll("\\.$", "");
        if (METADATA_HOSTS.contains(host) || host.endsWith(".internal")) {
            throw ApiException.unprocessable();
        }
        try {
            for (InetAddress address : InetAddress.getAllByName(host)) {
                if (!allowed(address)) {
                    throw ApiException.unprocessable();
                }
            }
        } catch (java.net.UnknownHostException exception) {
            // 暂不可解析时放行；真正投递仍受端点审批与出站校验约束。
        }
        return text;
    }

    private static boolean allowed(InetAddress address) {
        String literal = address.getHostAddress();
        if (METADATA_IPS.contains(literal)) {
            return false;
        }
        return !(address.isAnyLocalAddress() || address.isLinkLocalAddress()
                || address.isMulticastAddress());
    }
}
