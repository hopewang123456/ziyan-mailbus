package io.github.hopewang123456.mailbus.adapters.filestore;

import com.fasterxml.jackson.databind.JsonNode;
import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Locale;

/**
 * D16 批2：python 消息 → java {@link MsgRecord} 的唯一映射实现。
 *
 * <p>供迁移读取（{@code PythonStoreReader}）与在线读投影（{@code PythonInboxStore}）
 * 共用，避免两套字段口径漂移（D2：读侧宽容）。
 *
 * <ul>
 *   <li>state 优先 status（python SoT），未知值 → PENDING + warning；</li>
 *   <li>时间戳：带偏移按原样解析；无偏移按 Asia/Shanghai（python 进程时区）转 UTC；</li>
 *   <li>priority 缺省 normal。</li>
 * </ul>
 */
public final class PythonMessageCodec {

    private static final ZoneId PY_TZ = ZoneId.of("Asia/Shanghai");

    private PythonMessageCodec() {
    }

    /** 一条 python 消息 JSON → 强类型记录（宽松，不抛异常）。 */
    public static MsgRecord toRecord(JsonNode m, List<String> warns) {
        String id = m.path("id").asText();
        MessageState state = mapState(m.path("state").asText(m.path("status").asText("")), id, warns);
        MsgRecord.Priority prio = mapPriority(m.path("priority").asText("normal"));
        Instant created = mapTime(m.path("created_at").asText(null), id, warns);
        Instant updated = mapTime(firstNonBlank(
                m.path("updated_at").asText(null),
                m.path("acknowledged_at").asText(null)), id, warns);
        if (updated == Instant.EPOCH) {
            updated = created;
        }
        return new MsgRecord(
                id,
                m.path("to").asText(id),
                m.path("from").asText("system"),
                m.path("type").asText("notice"),
                m.path("content").asText(""),
                prio, state, created, updated);
    }

    /** python 状态词 → 枚举（含 java 侧新增的 python 独有投影态）。 */
    public static MessageState mapState(String rawState, String id, List<String> warns) {
        String raw = rawState == null ? "" : rawState.trim().toLowerCase(Locale.ROOT);
        return switch (raw) {
            case "", "pending" -> MessageState.PENDING;
            case "pushed" -> MessageState.PUSHED;
            case "processing" -> MessageState.PROCESSING;
            case "done" -> MessageState.DONE;
            case "acknowledged", "acked" -> MessageState.ACKNOWLEDGED;
            case "rejected" -> MessageState.REJECTED;
            case "archived" -> MessageState.ARCHIVED;
            case "received" -> MessageState.RECEIVED;
            case "resending" -> MessageState.RESENDING;
            case "failed" -> MessageState.FAILED;
            case "closed" -> MessageState.CLOSED;
            case "sent" -> MessageState.SENT;
            default -> {
                warns.add(id + ": unknown state '" + raw + "' -> PENDING");
                yield MessageState.PENDING;
            }
        };
    }

    public static MsgRecord.Priority mapPriority(String raw) {
        return switch (raw == null ? "" : raw.trim().toLowerCase(Locale.ROOT)) {
            case "urgent" -> MsgRecord.Priority.URGENT;
            case "high" -> MsgRecord.Priority.HIGH;
            case "low" -> MsgRecord.Priority.LOW;
            default -> MsgRecord.Priority.NORMAL;
        };
    }

    public static Instant mapTime(String raw, String id, List<String> warns) {
        if (raw == null || raw.isBlank()) {
            return Instant.EPOCH;
        }
        // python emits compact offsets (+0800); ISO_OFFSET_DATE_TIME wants +08:00
        String norm = raw.replaceAll("([+-]\\d{2})(\\d{2})$", "$1:$2");
        try {
            return OffsetDateTime.parse(norm, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant();
        } catch (DateTimeParseException ignored) {
            // fall through to offset-less handling
        }
        try {
            return LocalDateTime.parse(norm, DateTimeFormatter.ISO_LOCAL_DATE_TIME)
                    .atZone(PY_TZ).toInstant();
        } catch (DateTimeParseException e) {
            warns.add(id + ": unparsable time '" + raw + "' -> EPOCH");
            return Instant.EPOCH;
        }
    }

    private static String firstNonBlank(String a, String b) {
        return a != null && !a.isBlank() ? a : b;
    }
}
