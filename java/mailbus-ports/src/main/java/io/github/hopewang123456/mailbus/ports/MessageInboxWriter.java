package io.github.hopewang123456.mailbus.ports;

import io.github.hopewang123456.mailbus.domain.message.MsgRecord;

import java.util.List;
import java.util.Optional;

/**
 * D16 批3：消息写路径端口 —— 落 python {@code inbox/<agent>/inbox.json}（唯一 SoT）。
 *
 * <p>实现方必须：
 * <ul>
 *   <li>在跨进程文件锁内读改写（与 python {@code file_lock} 命中同一锁文件）；</li>
 *   <li>按 python 格式写（id {@code msg-YYYYMMDD-NNNNN}、时间戳 {@code +0800}、
 *       state/status 双轨）；</li>
 *   <li>每次写后重算顶层 {@code has_unread}（非终态存在即为 true）。</li>
 * </ul>
 */
public interface MessageInboxWriter {

    /** 旧 java 单文件消息（msg-v1 shard）回迁报告。 */
    record LegacyShardReport(int agents, int migrated, int skipped, List<String> warnings) { }

    /** 追加一条新消息（state=pending，python 新消息格式）。 */
    void append(MsgRecord record);

    /**
     * python {@code process_ack} 语义：status→acknowledged + acknowledged_at；
     * state 为空/pending 时，task/task_reply → processing（received_at），
     * 其它类型 → done（done_at）。返回投影后的记录。
     */
    Optional<MsgRecord> acknowledge(String messageId);

    /** python {@code process_mark_read} 语义：仅置 status=acknowledged，不动 state。返回命中消息 id。 */
    List<String> markRead(String agent, List<String> messageIds);

    /**
     * python pusher 语义：state/status→pushed，pushed_count+1，last_pushed_at=now。
     * 返回更新后的记录（消息不存在则为空）。
     */
    Optional<MsgRecord> markPushed(String messageId);

    /** 归档 settled 消息到 {@code archive/<agent>/backlog-<stamp>.json}，返回归档 id 列表。 */
    List<String> archiveSettled(String agent);

    /** D5：旧 java {@code <msg-id>.json} 一次性回迁进 inbox.json（幂等：id 已存在跳过）。 */
    LegacyShardReport migrateLegacyShards();
}
