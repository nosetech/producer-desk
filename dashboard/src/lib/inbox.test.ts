import { describe, expect, it } from "vitest";
import {
  DEFAULT_INBOX_KIND,
  INBOX_KINDS,
  INBOX_TITLE_MAX,
  canSubmitInbox,
  inboxKindMeta,
  sortInbox,
} from "./inbox";
import type { InboxItem } from "./types";

const item = (number: number, created_at: string): InboxItem => ({
  number,
  title: `t${number}`,
  kind: "bug",
  body: "",
  created_at,
});

describe("inbox", () => {
  it("種別は bug / enhancement / other の3択で、既定は機能アイデア", () => {
    expect(INBOX_KINDS.map((k) => k.kind)).toEqual([
      "bug",
      "enhancement",
      "other",
    ]);
    expect(DEFAULT_INBOX_KIND).toBe("enhancement");
    expect(inboxKindMeta("bug").label).toBe("バグ");
  });

  it("種別と一言メモが揃っているときだけ登録できる（本文は任意）", () => {
    expect(canSubmitInbox({ kind: "bug", title: "x", body: "" })).toBe(true);
    expect(canSubmitInbox({ kind: "", title: "x", body: "" })).toBe(false);
    expect(canSubmitInbox({ kind: "bug", title: "   ", body: "b" })).toBe(
      false,
    );
    expect(
      canSubmitInbox({
        kind: "other",
        title: "a".repeat(INBOX_TITLE_MAX + 1),
        body: "",
      }),
    ).toBe(false);
  });

  it("登録日時の新しい順に並べ、同時刻は番号の大きい順", () => {
    const sorted = sortInbox([
      item(1, "2026-11-01T00:00:00Z"),
      item(3, "2026-11-02T00:00:00Z"),
      item(2, "2026-11-02T00:00:00Z"),
    ]);
    expect(sorted.map((i) => i.number)).toEqual([3, 2, 1]);
  });
});
