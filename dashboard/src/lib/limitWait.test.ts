import { describe, expect, it } from "vitest";
import { formatResetAt, formatTimeLeft, limitResumeMessage } from "./limitWait";

const MIN = 60 * 1000;

describe("formatTimeLeft", () => {
  it("時間と分で表す", () => {
    expect(formatTimeLeft(135 * MIN)).toBe("あと2時間15分");
    expect(formatTimeLeft(120 * MIN)).toBe("あと2時間");
    expect(formatTimeLeft(5 * MIN)).toBe("あと5分");
  });
  it("端数は切り上げ、0以下は1分未満", () => {
    expect(formatTimeLeft(30 * 1000)).toBe("あと1分");
    expect(formatTimeLeft(0)).toBe("あと1分未満");
    expect(formatTimeLeft(-5 * MIN)).toBe("あと1分未満");
  });
});

describe("formatResetAt", () => {
  it("M/D HH:mm で表す", () => {
    const ms = new Date(2026, 10, 28, 9, 5).getTime();
    expect(formatResetAt(ms)).toBe("11/28 09:05");
  });
});

describe("limitResumeMessage", () => {
  it("先頭に/model行を独立した行として置く", () => {
    expect(limitResumeMessage("qwen3-coder")).toBe(
      "/model litellm:qwen3-coder\n\n利用リミットの解除を待たずに、このモデルで作業を再開してください。",
    );
  });
});
