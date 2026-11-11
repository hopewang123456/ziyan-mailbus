package io.github.hopewang123456.mailbus.ports;

import io.github.hopewang123456.mailbus.domain.message.MsgRecord;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * D16 批2：python {@code inbox/<agent>/inbox.json} 的读投影端口。
 *
 * <p>与 {@link MessageRepository} 的分工：repository 是 java 语义的强类型查询
 * （msg_index 投影/文件仓），本端口额外携带 python 原始消息字段（status 双轨、
 * pushed_count、attachments、task_id…），供 API 返回与 python 直读同形。
 *
 * <p>SoT 是 python 的 inbox.json；实现方必须容忍 python 的宽松格式（state/status
 * 双轨、+0800 时间戳、历史 list 形 inbox）。
 */
public interface MessageProjection {

    /** 一条消息的投影视图：强类型记录 + python 原始字段（只读）。 */
    record MessageView(String agent, MsgRecord record, Map<String, Object> raw) {}

    /** 有 inbox.json 的 agent（按名字排序）。 */
    List<String> agents();

    /** 单 agent 全部消息（文件内顺序，与 python 直读一致）。 */
    List<MessageView> messagesOf(String agent);

    /** inbox.json 顶层 has_unread 标志（python 直读口径）。 */
    boolean hasUnread(String agent);

    /** 未读数：非终态消息数（python {@code _count_unread} 同口径）。 */
    long unreadCount(String agent);

    /** 跨 agent 按 id 查找（python {@code handle_inbox_ack} 的跨 agent 定位语义）。 */
    Optional<MessageView> findById(String id);

    /** 聚合计数（status/stats 接口口径，等价 msg_index 的 GROUP BY）。 */
    List<MessageRepository.AgentStateCount> counts();

    /** 投影读取期告警（未知状态/坏时间戳），reconcile 报告用。 */
    default List<String> warnings() {
        return List.of();
    }
}
