import { describe, expect, it } from "vitest";
import {
  canApprove,
  initialPlanState,
  parsePlanStage,
  planReducer,
  showReview,
  type PlanState,
} from "./planFlow";

function run(
  state: PlanState,
  ...actions: Parameters<typeof planReducer>[1][]
) {
  return actions.reduce(planReducer, state);
}

describe("parsePlanStage", () => {
  it("キュー順位と作成中を解釈する", () => {
    expect(parsePlanStage("plan_queued:2")).toEqual({ kind: "queued", pos: 2 });
    expect(parsePlanStage("plan_running")).toEqual({ kind: "running" });
    expect(parsePlanStage("plan_queued:x")).toBeNull();
    expect(parsePlanStage(null)).toBeNull();
    expect(parsePlanStage("issue")).toBeNull();
  });
});

describe("planReducer", () => {
  const created = run(
    initialPlanState(),
    { type: "edit", patch: { want: "やりたい" } },
    { type: "start", op: "create" },
    { type: "stage", stage: "plan_queued:2" },
    { type: "stage", stage: "plan_running" },
    { type: "succeeded", title: "題", body: "本文" },
  );

  it("入力→待機→作成中→確認へ遷移する", () => {
    expect(created.phase).toBe("review");
    expect(created.ver).toBe(1);
    expect(created.wasQueued).toBe(true);
    expect(canApprove(created)).toBe(true);
    expect(showReview(created)).toBe(true);
  });

  it("待機中・作成中の表示は進捗ポーリングに従う", () => {
    const s = run(initialPlanState("x"), { type: "start", op: "create" });
    expect(s.phase).toBe("generating");
    const q = planReducer(s, { type: "stage", stage: "plan_queued:3" });
    expect(q).toMatchObject({ phase: "queued", queuePos: 3, wasQueued: true });
    expect(canApprove(q)).toBe(false);
  });

  it("AI修正を繰り返すと版と履歴が増え、反映中は直前の計画を残す", () => {
    const editing = run(created, {
      type: "edit",
      patch: { fix: "短くして", title: "手直し題" },
    });
    const revising = planReducer(editing, { type: "start", op: "revise" });
    expect(revising.pendingFix).toBe("短くして");
    expect(revising.fix).toBe("");
    expect(revising.title).toBe("手直し題");
    expect(showReview(revising)).toBe(true);
    expect(canApprove(revising)).toBe(false);

    const done = planReducer(revising, {
      type: "succeeded",
      title: "新題",
      body: "新本文",
    });
    expect(done).toMatchObject({
      ver: 2,
      history: ["短くして"],
      pendingFix: "",
    });
  });

  it("修正の失敗は直前の計画へ戻れ、修正指示が入力欄に戻る", () => {
    const revising = run(
      created,
      { type: "edit", patch: { fix: "直して" } },
      { type: "start", op: "revise" },
      { type: "failed", kind: "timeout", message: "t" },
    );
    expect(showReview(revising)).toBe(true);
    const back = planReducer(revising, { type: "back" });
    expect(back).toMatchObject({
      phase: "review",
      fix: "直して",
      pendingFix: "",
    });
  });

  it("作成の失敗は入力へ戻り、計画確認は出ない", () => {
    const failed = run(
      initialPlanState("x"),
      { type: "start", op: "create" },
      { type: "failed", kind: "parse", message: "p" },
    );
    expect(failed.err).toBe("parse");
    expect(showReview(failed)).toBe(false);
    expect(planReducer(failed, { type: "back" }).phase).toBe("input");
  });

  it("やり直すと計画を破棄して、やりたいことだけ残す", () => {
    expect(planReducer(created, { type: "redo" })).toEqual(
      initialPlanState("やりたい"),
    );
  });

  it("タイトルまたは本文が空だと承認できない", () => {
    expect(
      canApprove(run(created, { type: "edit", patch: { title: " " } })),
    ).toBe(false);
    expect(
      canApprove(run(created, { type: "edit", patch: { body: "" } })),
    ).toBe(false);
  });
});
