import { describe, expect, it } from "vitest";
import { buildQueueItems, queueAriaLabel, truncateQueueTitle } from "./queue";
import type { ProjectQueue, QueueEntry } from "./types";

const e = (number: number): QueueEntry => ({
  number,
  title: `t${number}`,
  label: null,
});

describe("buildQueueItems", () => {
  it("空キューは要素なし", () => {
    expect(buildQueueItems({ running: null, waiting: [] })).toEqual([]);
  });

  it("実行中のみ", () => {
    const items = buildQueueItems({ running: e(1), waiting: [] });
    expect(items.map((i) => i.kind)).toEqual(["running"]);
  });

  it("実行中なしで待機がある場合は空き枠を先頭に置く", () => {
    const items = buildQueueItems({ running: null, waiting: [e(2)] });
    expect(items.map((i) => i.kind)).toEqual(["slot", "sep", "waiting"]);
  });

  it("待機はFIFO順・番号は1始まりで、重複issueもそのまま並ぶ", () => {
    const items = buildQueueItems({
      running: e(1),
      waiting: [e(3), e(2), e(3)],
    });
    const waiting = items.filter((i) => i.kind === "waiting");
    expect(
      waiting.map((i) =>
        i.kind === "waiting" ? [i.entry.number, i.position] : [],
      ),
    ).toEqual([
      [3, 1],
      [2, 2],
      [3, 3],
    ]);
  });

  it("待機が5件までは省略せず、6件以上は先頭4件＋+Nにまとめる", () => {
    const five = buildQueueItems({
      running: e(1),
      waiting: [2, 3, 4, 5, 6].map(e),
    });
    expect(five.some((i) => i.kind === "more")).toBe(false);

    const eight = buildQueueItems({
      running: e(1),
      waiting: [2, 3, 4, 5, 6, 7, 8, 9].map(e),
    });
    expect(eight.filter((i) => i.kind === "waiting")).toHaveLength(4);
    expect(eight[eight.length - 1]).toEqual({
      kind: "more",
      count: 4,
      numbers: [6, 7, 8, 9],
    });
  });
});

describe("queueAriaLabel / truncateQueueTitle", () => {
  it("空・実行中あり・実行中なしの説明文", () => {
    const empty: ProjectQueue = { running: null, waiting: [] };
    expect(queueAriaLabel("a/b", empty)).toBe("a/b の実行キュー: 空");
    expect(queueAriaLabel("a/b", { running: e(1), waiting: [e(2)] })).toBe(
      "a/b の実行キュー: 実行中 #1、待機 1件",
    );
    expect(queueAriaLabel("a/b", { running: null, waiting: [e(2)] })).toBe(
      "a/b の実行キュー: 実行中なし、待機 1件",
    );
  });

  it("44文字を超えるタイトルは省略する", () => {
    expect(truncateQueueTitle("a".repeat(44))).toHaveLength(44);
    expect(truncateQueueTitle("a".repeat(45))).toBe(`${"a".repeat(43)}…`);
  });
});
