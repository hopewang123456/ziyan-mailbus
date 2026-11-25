package io.github.hopewang123456.mailbus.workflow;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/** 条件规则求值：与 Python 版保持同一白名单和比较语义。 */
@Component
public class TaskConditions {

    private static final List<String> PREFIXES =
            List.of("result.", "task.", "node.", "context.", "artifacts.");

    private final ObjectMapper objectMapper;

    public TaskConditions(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public Object parseResult(String text) {
        if (text == null) {
            return null;
        }
        try {
            return objectMapper.readValue(text, Object.class);
        } catch (Exception exception) {
            return text;
        }
    }

    public boolean isFailedResult(String text) {
        Object parsed = parseResult(text);
        if (!(parsed instanceof Map<?, ?> map)) {
            return false;
        }
        Object status = map.get("status");
        String value = status == null ? "" : status.toString().toLowerCase();
        return "failed".equals(value) || "rejected".equals(value);
    }

    public boolean evaluate(String condition, Map<String, Object> context) {
        if (condition == null || condition.isBlank()) {
            return true;
        }
        try {
            Object rule = objectMapper.readValue(condition, Object.class);
            return match(rule, context);
        } catch (Exception exception) {
            return false;
        }
    }

    private boolean match(Object rule, Map<String, Object> context) {
        if (!(rule instanceof Map<?, ?> map)) {
            return false;
        }
        if (map.containsKey("and") && map.get("and") instanceof List<?> items) {
            return items.stream().allMatch(item -> match(item, context));
        }
        if (map.containsKey("or") && map.get("or") instanceof List<?> items) {
            return items.stream().anyMatch(item -> match(item, context));
        }
        Object name = map.get("field");
        if (!(name instanceof String field)
                || PREFIXES.stream().noneMatch(field::startsWith)) {
            return false;
        }
        Object op = map.get("op");
        return compare(resolve(field, context), op == null ? "" : op.toString(),
                map.get("value"));
    }

    private Object resolve(String name, Map<String, Object> context) {
        int dot = name.indexOf('.');
        Object value = context.get(name.substring(0, dot));
        for (String part : name.substring(dot + 1).split("\\.")) {
            if (value instanceof Map<?, ?> map) {
                value = map.get(part);
            } else {
                return null;
            }
        }
        return value;
    }

    private boolean compare(Object left, String op, Object right) {
        try {
            return switch (op) {
                case "==" -> equalValues(left, right);
                case "!=" -> !equalValues(left, right);
                case ">", ">=", "<", "<=" -> ordered(left, right, op);
                case "contains" -> left != null && contains(left, right);
                case "in" -> right instanceof List<?> items && items.contains(left);
                case "not_in" -> right instanceof List<?> items && !items.contains(left);
                case "startsWith" -> left instanceof String text
                        && text.startsWith(String.valueOf(right));
                case "endsWith" -> left instanceof String text
                        && text.endsWith(String.valueOf(right));
                case "regex" -> left instanceof String text
                        && Pattern.compile(String.valueOf(right)).matcher(text).find();
                default -> false;
            };
        } catch (Exception exception) {
            return false;
        }
    }

    private boolean equalValues(Object left, Object right) {
        if (left instanceof Number leftNumber && right instanceof Number rightNumber) {
            return Double.compare(leftNumber.doubleValue(), rightNumber.doubleValue()) == 0;
        }
        if (left == null) {
            return right == null;
        }
        return left.equals(right);
    }

    private boolean contains(Object left, Object right) {
        if (left instanceof String text) {
            return right != null && text.contains(right.toString());
        }
        if (left instanceof List<?> items) {
            return items.contains(right);
        }
        if (left instanceof Map<?, ?> map) {
            return map.containsKey(right) || map.containsValue(right);
        }
        return false;
    }

    private boolean ordered(Object left, Object right, String op) {
        if (!(left instanceof Number leftNumber) || !(right instanceof Number rightNumber)) {
            return false;
        }
        double a = leftNumber.doubleValue();
        double b = rightNumber.doubleValue();
        return switch (op) {
            case ">" -> a > b;
            case ">=" -> a >= b;
            case "<" -> a < b;
            default -> a <= b;
        };
    }
}
