package io.github.hopewang123456.mailbus.auth;

import io.github.hopewang123456.mailbus.common.ApiException;
import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** 离线语义：offline 只是心跳超时（离席），不剥夺能力；pending/注销才不可用。 */
class AuthzOfflineTest {

    private static Actor actor(String status, String... capabilities) {
        return new Actor(
                "emp_test", "测试账号", "human", status, null, "global", "", true,
                Set.of(capabilities));
    }

    @Test
    void offlineAccountKeepsCapabilities() {
        Actor offline = actor("offline", Authz.LOG_READ);

        assertThatCode(() -> Authz.ensureActive(offline)).doesNotThrowAnyException();
        assertThatCode(() -> Authz.ensureAllowed(
                offline, Authz.LOG_READ, Authz.Resource.of("log"))).doesNotThrowAnyException();
        assertThatCode(() -> Authz.ensureAnyAllowed(
                offline, Set.of(Authz.LOG_READ), Authz.Resource.of("log")))
                .doesNotThrowAnyException();
    }

    @Test
    void pendingAccountIsRejected() {
        Actor pending = actor("pending", Authz.LOG_READ);

        assertThatThrownBy(() -> Authz.ensureActive(pending))
                .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> Authz.ensureAllowed(
                pending, Authz.LOG_READ, Authz.Resource.of("log")))
                .isInstanceOf(ApiException.class);
    }

    @Test
    void offlineAccountStillNeedsTheCapability() {
        Actor offline = actor("offline", Authz.LOG_READ);

        assertThatThrownBy(() -> Authz.ensureAllowed(
                offline, Authz.ORG_MANAGE, Authz.Resource.of("org")))
                .isInstanceOf(ApiException.class);
    }
}
