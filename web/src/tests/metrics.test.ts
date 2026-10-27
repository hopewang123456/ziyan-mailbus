import { describe, expect, it } from "vitest";
import { formatValue } from "../components/metrics/format";

describe("MetricCard formatValue（指标卡数值格式化）", () => {
  it("整数原样", () => {
    expect(formatValue(4)).toBe("4");
    expect(formatValue(0)).toBe("0");
  });
  it("千位缩写 k/M", () => {
    expect(formatValue(1497)).toBe("1.5k");
    expect(formatValue(2_400_000)).toBe("2.4M");
  });
  it("小数保留一位", () => {
    expect(formatValue(23.34)).toBe("23.3");
  });
});
