import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILTER,
  FILTER_ALL,
  FILTER_ORPHAN,
  buildFilterOptions,
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
