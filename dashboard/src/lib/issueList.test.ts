import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILTER,
  FILTER_ALL,
  FILTER_ORPHAN,
  buildFilterOptions,
  buildMetaFilterOptions,
  filterByMeta,
} from "./issueList";
import type { ProjectIssue } from "./types";

function issue(over: Partial<ProjectIssue>): ProjectIssue {
  return {
    number: 1,
    label: "status:todo",
    is_orphaned: false,
    ...over,
  } as ProjectIssue;
}

describe("buildFilterOptions", () => {
  it("「すべて」は「完了」の右隣（末尾）に並ぶ", () => {
    const keys = buildFilterOptions([issue({})], false).map((o) => o.key);
    expect(keys).toEqual([
      "status:todo",
      "status:in-progress",
      "needs-human-decision",
      "status:in-review",
      "untagged",
      "status:closed",
      FILTER_ALL,
    ]);
  });

  it("孤立issueがあれば「停止の可能性」が未着手の前に来る", () => {
    const keys = buildFilterOptions([issue({ is_orphaned: true })], false).map(
      (o) => o.key,
    );
    expect(keys[0]).toBe(FILTER_ORPHAN);
    expect(keys[keys.length - 1]).toBe(FILTER_ALL);
  });

  it("初期フィルタは未着手", () => {
    expect(DEFAULT_FILTER).toBe("status:todo");
  });
});

describe("buildMetaFilterOptions", () => {
  const issues = [
    issue({ number: 1, milestone: "v1", tags: ["bug", "enhancement"] }),
    issue({ number: 2, milestone: "v1", tags: ["bug"] }),
    issue({ number: 3, milestone: null }),
  ];

  it("件数付きで返し、tags未設定の古いデータも扱える", () => {
    expect(buildMetaFilterOptions(issues)).toEqual({
      milestones: [{ value: "v1", count: 2 }],
      tags: [
        { value: "bug", count: 2 },
        { value: "enhancement", count: 1 },
      ],
    });
  });

  it("選択肢は全体から決め、件数は渡した一覧（状態フィルタ後）で数える", () => {
    expect(buildMetaFilterOptions(issues, [issues[1]])).toEqual({
      milestones: [{ value: "v1", count: 1 }],
      tags: [
        { value: "bug", count: 1 },
        { value: "enhancement", count: 0 },
      ],
    });
  });

  it("オープン中のマイルストーンだけを選択肢にする（issue #308）", () => {
    const withClosed = [
      issue({ number: 1, milestone: "v1" }),
      issue({ number: 2, milestone: "v2" }),
      issue({ number: 3, milestone: "old" }),
    ];
    expect(
      buildMetaFilterOptions(withClosed, withClosed, ["v1", "v2"]).milestones,
    ).toEqual([
      { value: "v1", count: 1 },
      { value: "v2", count: 1 },
    ]);
    expect(
      buildMetaFilterOptions(withClosed, withClosed, []).milestones,
    ).toEqual([]);
  });

  it("オープン中一覧がnull（取得失敗）なら絞り込まない", () => {
    const withClosed = [
      issue({ number: 1, milestone: "v1" }),
      issue({ number: 3, milestone: "old" }),
    ];
    expect(
      buildMetaFilterOptions(withClosed, withClosed, null).milestones.map(
        (m) => m.value,
      ),
    ).toEqual(["old", "v1"]);
  });

  it("マイルストーン・タグが無ければ空", () => {
    expect(buildMetaFilterOptions([issue({})])).toEqual({
      milestones: [],
      tags: [],
    });
  });
});

describe("filterByMeta", () => {
  const issues = [
    issue({ number: 1, milestone: "v1", tags: ["bug"] }),
    issue({ number: 2, milestone: "v1", tags: ["enhancement"] }),
    issue({ number: 3, milestone: "v2", tags: ["bug", "enhancement"] }),
    issue({ number: 4 }),
  ];
  const nums = (rows: ProjectIssue[]) => rows.map((i) => i.number);

  it("選択0件なら絞り込まない（OR/ANDとも）", () => {
    expect(nums(filterByMeta(issues, [], [], "or"))).toEqual([1, 2, 3, 4]);
    expect(nums(filterByMeta(issues, [], [], "and"))).toEqual([1, 2, 3, 4]);
  });

  it("ORは選択のいずれかに該当するissueを残す", () => {
    expect(nums(filterByMeta(issues, ["v2"], ["bug"], "or"))).toEqual([1, 3]);
    expect(nums(filterByMeta(issues, ["v1", "v2"], [], "or"))).toEqual([
      1, 2, 3,
    ]);
  });

  it("ANDは選択のすべてに該当するissueを残す", () => {
    expect(nums(filterByMeta(issues, ["v1"], ["bug"], "and"))).toEqual([1]);
    expect(
      nums(filterByMeta(issues, [], ["bug", "enhancement"], "and")),
    ).toEqual([3]);
  });

  it("ANDで複数のマイルストーンを選ぶと0件になる", () => {
    expect(filterByMeta(issues, ["v1", "v2"], [], "and")).toEqual([]);
  });

  it("1つだけの選択はOR/ANDで結果が同じ", () => {
    expect(nums(filterByMeta(issues, [], ["bug"], "and"))).toEqual(
      nums(filterByMeta(issues, [], ["bug"], "or")),
    );
  });
});
