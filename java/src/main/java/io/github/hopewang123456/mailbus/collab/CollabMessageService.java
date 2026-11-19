package io.github.hopewang123456.mailbus.collab;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.messaging.MessageDtos;
import io.github.hopewang123456.mailbus.messaging.MessagingService;
import org.springframework.stereotype.Service;

import java.util.List;

/** 协同消息用例：在结对范围内发送与检索消息，消息本体仍写入 msg_messages。 */
@Service
public class CollabMessageService {

    private final MessagingService messaging;
    private final PairRepository pairs;

    public CollabMessageService(MessagingService messaging, PairRepository pairs) {
        this.messaging = messaging;
        this.pairs = pairs;
    }

    public MessageDtos.MessageOut send(Actor actor, CollabDtos.CollabMessageIn input) {
        PairRepository.Row pair = load(actor, input.pairId());
        if (!"active".equals(pair.state())) {
            throw ApiException.conflict("invalid_state", "结对已结束，不能继续发送协同消息");
        }
        String kind = input.kind() == null || input.kind().isBlank() ? "note" : input.kind();
        String channel = input.channel() == null || input.channel().isBlank()
                ? "file_bus" : input.channel();
        return messaging.send(actor,
                new MessageDtos.MessageIn(input.body(), input.recipientId(), kind, channel),
                channel, pair.pairId());
    }

    public List<MessageDtos.MessageOut> list(Actor actor, String pairId, int limit) {
        if (pairId != null && !pairId.isBlank()) {
            load(actor, pairId);
        }
        return messaging.listCollab(actor, pairId, limit);
    }

    /** 公开大屏投影：只按结对读取，不校验调用者。 */
    public List<MessageDtos.MessageOut> publicList(String pairId, int limit) {
        return messaging.listPublicCollab(pairId, limit);
    }

    private PairRepository.Row load(Actor actor, String pairId) {
        PairRepository.Row pair = pairs.get(pairId)
                .orElseThrow(() -> ApiException.notFound("结对不存在"));
        if (actor.has(Authz.ALL) || pair.involves(actor.employeeId())) {
            return pair;
        }
        throw ApiException.forbidden("只能访问自己参与的结对");
    }
}
