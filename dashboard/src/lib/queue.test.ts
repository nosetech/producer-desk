import { describe, expect, it } from "vitest";
import {
  buildQueueItems,
  canOpenPlan,
  planOpenHint,
  queueAriaLabel,
  queueEntryAriaLabel,
  queueEntryShortLabel,
  truncateQueueTitle,
} from "./queue";
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
      labels: ["#6", "#7", "#8", "#9"],
    });
  });
});

const plan = (number: number, title: string | null = "計画"): QueueEntry => ({
  number,
  title,
  label: null,
  kind: "plan",
  plan_job_id: `p${-number}`,
  inbox_issue_number: null,
});

describe("AI計画ジョブ（issue #335）", () => {
  it("計画ジョブも自走タスクと同じ列にFIFO順で並び、待機順位が通しで振られる", () => {
    const items = buildQueueItems({
      running: plan(-1),
      waiting: [e(2), plan(-2), e(3)],
    });
    expect(items[0]).toEqual({ kind: "running", key: "r", entry: plan(-1) });
    expect(
      items.flatMap((i) =>
        i.kind === "waiting"
          ? [[queueEntryShortLabel(i.entry), i.position]]
          : [],
      ),
    ).toEqual([
      ["#2", 1],
      ["AI計画", 2],
      ["#3", 3],
    ]);
  });

  it("+Nの省略表記で計画ジョブは「AI計画」と表記する", () => {
    const items = buildQueueItems({
      running: e(1),
      waiting: [e(2), e(3), e(4), e(5), e(6), plan(-1), e(7)],
    });
    expect(items[items.length - 1]).toEqual({
      kind: "more",
      count: 3,
      labels: ["#6", "AI計画", "#7"],
    });
  });

  it("aria-labelで実行中の計画ジョブを「AI計画」と表記する", () => {
    expect(queueAriaLabel("a/b", { running: plan(-3), waiting: [] })).toBe(
      "a/b の実行キュー: 実行中 AI計画、待機 0件",
    );
    expect(
      queueAriaLabel("a/b", { running: e(1), waiting: [plan(-1), e(2)] }),
    ).toBe("a/b の実行キュー: 実行中 #1、待機 2件（うちAI計画 1件）");
  });

  it("アイコンの読み上げは計画ジョブを「AI計画」と依頼文で表す", () => {
    expect(queueEntryAriaLabel(plan(-1, "画面を作る"), "実行中")).toBe(
      "AI計画 画面を作る — 実行中",
    );
    expect(queueEntryAriaLabel(plan(-1, null), "待機中 · 2番目")).toBe(
      "AI計画 — 待機中 · 2番目",
    );
    expect(queueEntryAriaLabel(e(3), "実行中")).toBe("#3 t3 — 実行中");
  });

  it("計画を開けるのはinbox由来で既に計画を持つ（修正中）ジョブのみ", () => {
    const inbox = { ...plan(-1), inbox_issue_number: 12 };
    expect(canOpenPlan(inbox)).toBe(false);
    expect(canOpenPlan({ ...inbox, plan_revising: true })).toBe(true);
    expect(canOpenPlan({ ...plan(-1), plan_revising: true })).toBe(false);
    expect(planOpenHint(inbox)).toContain("inbox");
    expect(planOpenHint(plan(-1))).toContain("未承認の計画");
  });

  it("kind省略（旧オーケストレータ）は自走タスクとして扱う", () => {
    expect(queueEntryShortLabel(e(5))).toBe("#5");
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
