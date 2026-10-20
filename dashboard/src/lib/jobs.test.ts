import { describe, expect, it } from "vitest";
import {
  canStartJob,
  failureMessage,
  findIssueJob,
  issueKey,
  progressCount,
  removeJob,
  stageIndex,
  updateJob,
  type Job,
} from "./jobs";

function job(over: Partial<Job> = {}): Job {
  return {
    key: "o/a#1",
    kind: "approve",
    repo: "o/a",
    number: 1,
    title: "t",
    stages: [
      { key: "comment", label: "c", note: "n" },
      { key: "label", label: "l", note: "n" },
      { key: "dispatch", label: "d", note: "n" },
    ],
    status: "running",
    polledStage: null,
    progressId: "p",
    ...over,
  };
}

describe("jobs", () => {
  it("別repo・別issueの操作は同時に開始できる", () => {
    const jobs = [job()];
    expect(canStartJob(jobs, "o/b", 1)).toBe(true);
    expect(canStartJob(jobs, "o/a", 2)).toBe(true);
  });

  it("同一issueへの二重操作は拒否される（失敗中も含む）", () => {
    expect(canStartJob([job()], "o/a", 1)).toBe(false);
    expect(canStartJob([job({ status: "error" })], "o/a", 1)).toBe(false);
  });

  it("新規作成は常に開始できる", () => {
    expect(canStartJob([job()], "o/a", undefined)).toBe(true);
  });

  it("issueごとにジョブを引ける", () => {
    const jobs = [job(), job({ key: "o/b#1", repo: "o/b" })];
    expect(findIssueJob(jobs, "o/b", 1)?.key).toBe("o/b#1");
    expect(findIssueJob(jobs, "o/b", 2)).toBeUndefined();
    expect(issueKey("o/a", 1)).toBe("o/a#1");
  });

  it("更新・削除は対象キーだけに作用する", () => {
    const jobs = [job(), job({ key: "o/b#1", repo: "o/b" })];
    const upd = updateJob(jobs, "o/b#1", { status: "error" });
    expect(upd[0].status).toBe("running");
    expect(upd[1].status).toBe("error");
    expect(removeJob(upd, "o/a#1").map((j) => j.key)).toEqual(["o/b#1"]);
  });

  it("失敗文言にissueが特定できる", () => {
    expect(failureMessage(job())).toBe("a #1 の承認に失敗しました。");
    expect(failureMessage(job({ kind: "new", number: undefined }))).toBe(
      "a（新規） のissueの作成に失敗しました。",
    );
  });

  it("進捗件数は最新の完了段階から算出する", () => {
    expect(stageIndex(job())).toBe(-1);
    expect(progressCount(job(), -1)).toBe("1 / 3");
    const j = job({ polledStage: "label" });
    expect(progressCount(j, stageIndex(j))).toBe("3 / 3");
    const e = job({ polledStage: "comment", status: "error" });
    expect(progressCount(e, stageIndex(e))).toBe("1 / 3");
  });
});
