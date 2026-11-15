import { describe, expect, it } from "vitest";
import {
  MAX_META_ISSUES,
  buildMetaInput,
  canApplyMeta,
  pruneSelection,
  selectAllState,
  summarizeMetaResult,
  toggleLabelChoice,
  toggleSelectAll,
  toggleSelected,
} from "./issueMeta";

const keep = { mode: "keep" } as const;

describe("issueMeta", () => {
  it("すべて選択の状態は表示行だけで判定する", () => {
    expect(selectAllState([], new Set([1]))).toBe("none");
    expect(selectAllState([1, 2], new Set())).toBe("none");
    expect(selectAllState([1, 2], new Set([1, 9]))).toBe("some");
    expect(selectAllState([1, 2], new Set([1, 2, 9]))).toBe("all");
  });

  it("すべて選択の切替は非表示の選択済み行を維持する", () => {
    expect(toggleSelectAll([1, 2], new Set([9]))).toEqual(new Set([1, 2, 9]));
    expect(toggleSelectAll([1, 2], new Set([1, 9]))).toEqual(
      new Set([1, 2, 9]),
    );
    expect(toggleSelectAll([1, 2], new Set([1, 2, 9]))).toEqual(new Set([9]));
  });

  it("個別の選択切替とフィルタ後の整理", () => {
    expect(toggleSelected(new Set([1]), 2)).toEqual(new Set([1, 2]));
    expect(toggleSelected(new Set([1]), 1)).toEqual(new Set());
    expect(pruneSelection(new Set([1, 2, 3]), [2, 3, 4])).toEqual(
      new Set([2, 3]),
    );
  });

  it("追加と削除に同じラベルを指定できない", () => {
    expect(toggleLabelChoice("add", "bug", [], ["bug", "docs"])).toEqual({
      add: ["bug"],
      remove: ["docs"],
    });
    expect(toggleLabelChoice("remove", "bug", ["bug"], [])).toEqual({
      add: [],
      remove: ["bug"],
    });
    expect(toggleLabelChoice("add", "bug", ["bug"], [])).toEqual({
      add: [],
      remove: [],
    });
  });

  it("変更なし・未選択・上限超過は適用できない", () => {
    const draft = { milestone: keep, addLabels: ["bug"], removeLabels: [] };
    expect(canApplyMeta(new Set(), draft)).toBe(false);
    expect(canApplyMeta(new Set([1]), { ...draft, addLabels: [] })).toBe(false);
    expect(canApplyMeta(new Set([1]), draft)).toBe(true);
    expect(
      canApplyMeta(new Set([1]), {
        milestone: { mode: "clear" },
        addLabels: [],
        removeLabels: [],
      }),
    ).toBe(true);
    const many = new Set(
      Array.from({ length: MAX_META_ISSUES + 1 }, (_, i) => i),
    );
    expect(canApplyMeta(many, draft)).toBe(false);
  });

  it("リクエストは番号昇順で組み立てる", () => {
    expect(
      buildMetaInput(new Set([3, 1]), {
        milestone: { mode: "set", value: "v1" },
        addLabels: ["bug"],
        removeLabels: ["docs"],
      }),
    ).toEqual({
      issues: [1, 3],
      milestone: { mode: "set", value: "v1" },
      add_labels: ["bug"],
      remove_labels: ["docs"],
    });
  });

  it("結果の要約は失敗分だけ選択に残す", () => {
    const ok = summarizeMetaResult({ succeeded: [1, 2], failed: [] });
    expect(ok).toMatchObject({
      message: "2件を更新しました",
      hasFailure: false,
    });
    expect(ok.remaining.size).toBe(0);
    const part = summarizeMetaResult({
      succeeded: [1],
      failed: [{ number: 2, error: "x" }],
    });
    expect(part.message).toBe("1件成功・1件失敗");
    expect(part.remaining).toEqual(new Set([2]));
    expect(part.hasFailure).toBe(true);
  });
});
