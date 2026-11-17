import { describe, expect, it } from "vitest";
import type { PlanJob } from "./api";
import {
  canApprove,
  derivePlanView,
  hasActivePlan,
  initialPlanState,
  planBadge,
  planReducer,
  showReview,
  type PlanState,
} from "./planFlow";

function job(over: Partial<PlanJob> = {}): PlanJob {
  return {
    id: "a1",
    repo: "o/r",
    request: "やりたい",
    model: null,
    inboxIssueNumber: null,
    status: "queued",
    result: null,
    error: null,
    history: [],
    pendingInstruction: null,
    version: 0,
    queuePosition: null,
    createdAt: "t",
    updatedAt: "t",
    ...over,
  };
}

function run(
  state: PlanState,
  ...actions: Parameters<typeof planReducer>[1][]
) {
  return actions.reduce(planReducer, state);
}

describe("derivePlanView", () => {
  it("ジョブが無ければ入力ステップ", () => {
    expect(derivePlanView(null)).toMatchObject({ phase: "input", ver: 0 });
  });

  it("キュー待ち（順位つき）・作成中・確認待ちをジョブ状態から導出する", () => {
    expect(
      derivePlanView(job({ status: "queued", queuePosition: 2 })),
    ).toMatchObject({ phase: "queued", queuePos: 2, op: "create" });
    expect(derivePlanView(job({ status: "running" }))).toMatchObject({
      phase: "generating",
      queuePos: 0,
    });
    expect(
      derivePlanView(
        job({
          status: "succeeded",
          version: 1,
          result: { title: "題", body: "本文" },
        }),
      ),
    ).toMatchObject({ phase: "review", ver: 1 });
  });

  it("修正中は直前の計画を残し、反映中の指示を履歴から分ける", () => {
    const view = derivePlanView(
      job({
        status: "running",
        version: 1,
        result: { title: "題", body: "本文" },
        history: [
          { instruction: "一回目", at: "t" },
          { instruction: "二回目", at: "t" },
        ],
        pendingInstruction: "二回目",
      }),
    );
    expect(view).toMatchObject({
      phase: "generating",
      op: "revise",
      pendingFix: "二回目",
      history: ["一回目"],
      ver: 1,
    });
    expect(showReview(view)).toBe(true);
  });

  it("失敗は種別つきで、初回の失敗には確認欄を出さない", () => {
    const failed = derivePlanView(
      job({ status: "failed", error: { code: "timeout", message: "m" } }),
    );
    expect(failed).toMatchObject({
      phase: "error",
      err: "timeout",
      op: "create",
    });
    expect(showReview(failed)).toBe(false);
  });

  it("修正の失敗は直前の計画を残して確認欄を出す", () => {
    const view = derivePlanView(
      job({
        status: "failed",
        version: 1,
        result: { title: "題", body: "本文" },
        history: [{ instruction: "壊す", at: "t" }],
        error: { code: "parse", message: "m" },
      }),
    );
    expect(view).toMatchObject({
      phase: "error",
      op: "revise",
      pendingFix: "壊す",
      history: [],
    });
    expect(showReview(view)).toBe(true);
  });

  it("再起動で中断されたジョブはinterruptedの失敗", () => {
    expect(
      derivePlanView(
        job({ status: "failed", error: { code: "interrupted", message: "m" } }),
      ).err,
    ).toBe("interrupted");
  });
});

describe("planReducer", () => {
  const succeeded = job({
    status: "succeeded",
    version: 1,
    result: { title: "題", body: "本文" },
  });

  it("確認待ちの結果をタイトル・本文へ反映し、承認可能になる", () => {
    const s = run(initialPlanState("x"), { type: "sync", job: succeeded });
    expect(s).toMatchObject({ title: "題", body: "本文" });
    expect(canApprove(s)).toBe(true);
  });

  it("同じ版の再取得（ポーリング）では編集中の内容を上書きしない", () => {
    const s = run(
      initialPlanState(),
      { type: "sync", job: succeeded },
      { type: "edit", patch: { title: "編集中" } },
      { type: "sync", job: { ...succeeded, updatedAt: "t2" } },
    );
    expect(s.title).toBe("編集中");
  });

  it("修正で新しい版が届いたら編集欄を置き換える", () => {
    const s = run(
      initialPlanState(),
      { type: "sync", job: succeeded },
      { type: "edit", patch: { title: "編集中" } },
      {
        type: "sync",
        job: {
          ...succeeded,
          version: 2,
          result: { title: "題2", body: "本文2" },
        },
      },
    );
    expect(s).toMatchObject({ title: "題2", body: "本文2" });
  });

  it("修正中・失敗中は承認できない", () => {
    const s = run(initialPlanState(), {
      type: "sync",
      job: { ...succeeded, status: "running" },
    });
    expect(canApprove(s)).toBe(false);
  });

  it("タイトル・本文が空なら承認できない", () => {
    const s = run(
      initialPlanState(),
      { type: "sync", job: succeeded },
      { type: "edit", patch: { body: "  " } },
    );
    expect(canApprove(s)).toBe(false);
  });

  it("破棄されたジョブ（null）で入力に戻り、やりたいことは保持する", () => {
    const s = run(
      initialPlanState("やりたい"),
      { type: "sync", job: succeeded },
      { type: "sync", job: null },
    );
    expect(derivePlanView(s.job).phase).toBe("input");
    expect(s.want).toBe("やりたい");
    expect(run(s, { type: "reset" }).title).toBe("");
  });

  it("修正指示の送信で入力欄を空にする", () => {
    const s = run(
      initialPlanState(),
      { type: "edit", patch: { fix: "短く" } },
      { type: "revised" },
    );
    expect(s.fix).toBe("");
  });
});

describe("一覧表示", () => {
  it("ジョブ状態を表示用バッジへ対応づける", () => {
    expect(planBadge(job({ status: "queued" }))).toBe("queued");
    expect(planBadge(job({ status: "running" }))).toBe("running");
    expect(planBadge(job({ status: "succeeded" }))).toBe("review");
    expect(planBadge(job({ status: "failed" }))).toBe("failed");
  });

  it("実行中のジョブがあるときだけポーリング継続と判断する", () => {
    expect(hasActivePlan([job({ status: "succeeded" })])).toBe(false);
    expect(
      hasActivePlan([job({ status: "failed" }), job({ status: "running" })]),
    ).toBe(true);
  });
});
