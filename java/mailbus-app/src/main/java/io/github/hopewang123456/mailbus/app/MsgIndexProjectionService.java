package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.ports.MessageProjection;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.util.ArrayList;
import java.util.List;

/**
 * D16 批2：msg_index 投影全量重建（files lead，索引可丢弃）。
 *
 * <p>python {@code inbox/<agent>/inbox.json} 是唯一消息 SoT；java SQLite
 * {@code msg_index} 降级为投影缓存——启动/定时/CLI 均可全量重刷，重建期空洞
 * 由下一次重建补齐（D4）。
 */
public class MsgIndexProjectionService {

    public record Report(int agents, int messages, int warnings, List<String> warningSample) {}

    private final MessageProjection source;
    private final MessageRepository index;

    public MsgIndexProjectionService(MessageProjection source, MessageRepository index) {
        this.source = source;
        this.index = index;
    }

    /** 清空 msg_index 并按 python SoT 全量重写。 */
    public Report rebuild() {
        List<String> agents = source.agents();
        List<MsgRecord> records = new ArrayList<>();
        for (String agent : agents) {
            for (MessageProjection.MessageView v : source.messagesOf(agent)) {
                records.add(v.record());
            }
        }
        index.replaceAll(records);
        List<String> warnings = source.warnings();
        return new Report(agents.size(), records.size(), warnings.size(),
                warnings.stream().limit(5).toList());
    }
}
