// 「AIに計画してもらう」の画面状態（issue #287・#299）。
// 計画の生成はオーケストレータ側のキューでバックグラウンド実行され、結果は計画ジョブとして
// 保持される（承認・破棄まで残る）。画面の状態（入力→待機中→作成中→確認→失敗）は、ジョブの
// 状態（`PlanJob`）から導出する。ここには、ユーザーが編集中の入力（やりたいこと・タイトル・
// 本文・修正指示）と、最後に反映したジョブの版だけを持つ（UI・通信から切り離してテストできる）。

import type { PlanJob, PlanJobErrorCode } from "./api";

export type PlanPhase = "input" | "queued" | "generating" | "review" | "error";
export type PlanOp = "create" | "revise";
export type PlanErrorKind = PlanJobErrorCode;

export interface PlanState {
  /** サーバー側のジョブ。まだ依頼していない（入力中）ならnull。 */
  job: PlanJob | null;
  want: string;
  title: string;
  body: string;
  fix: string;
  /** title/bodyへ最後に反映したジョブの版（`<id>:<version>`）。 */
  syncedKey: string | null;
}

export function initialPlanState(want = ""): PlanState {
  return { job: null, want, title: "", body: "", fix: "", syncedKey: null };
}

export type PlanAction =
  | {
      type: "edit";
      patch: Partial<Pick<PlanState, "want" | "title" | "body" | "fix">>;
    }
  /** サーバーのジョブ状態を反映する（ポーリング結果・依頼直後）。nullは破棄された。 */
  | { type: "sync"; job: PlanJob | null }
  /** 修正指示を投入した（入力欄を空にする）。 */
  | { type: "revised" }
  | { type: "reset"; want?: string };

function jobKey(job: PlanJob): string {
  return `${job.id}:${job.version}`;
}

export function planReducer(state: PlanState, action: PlanAction): PlanState {
  switch (action.type) {
    case "edit":
      return { ...state, ...action.patch };
    case "sync": {
      const { job } = action;
      if (!job) return { ...state, job: null, syncedKey: null };
      // 新しい版の結果が届いたときだけ編集欄を置き換える（編集中の内容を上書きしない）。
      if (job.result && state.syncedKey !== jobKey(job)) {
        return {
          ...state,
          job,
          title: job.result.title,
          body: job.result.body,
          syncedKey: jobKey(job),
        };
      }
      return { ...state, job };
    }
    case "revised":
      return { ...state, fix: "" };
    case "reset":
      return initialPlanState(action.want ?? state.want);
  }
}

export interface PlanView {
  phase: PlanPhase;
  op: PlanOp;
  /** キュー待ちの順位（1始まり）。待機中でなければ0。 */
  queuePos: number;
  err: PlanErrorKind | null;
  errMessage: string;
  /** 計画の版（0=未作成）。 */
  ver: number;
  /** 反映済みの修正指示の履歴。 */
  history: string[];
  /** 反映中（または失敗した）修正指示。 */
  pendingFix: string;
}

/** ジョブの状態から画面状態を導出する。 */
export function derivePlanView(job: PlanJob | null): PlanView {
  if (!job) {
    return {
      phase: "input",
      op: "create",
      queuePos: 0,
      err: null,
      errMessage: "",
      ver: 0,
      history: [],
      pendingFix: "",
    };
  }
  const all = job.history.map((h) => h.instruction);
  const revise = job.result !== null && job.status !== "succeeded";
  // 修正の実行中・失敗では、最後の指示がまだ反映されていない。
  const pendingFix = revise ? (all[all.length - 1] ?? "") : "";
  const history = revise ? all.slice(0, -1) : all;
  const phase: PlanPhase =
    job.status === "queued"
      ? "queued"
      : job.status === "running"
        ? "generating"
        : job.status === "failed"
          ? "error"
          : "review";
  return {
    phase,
    op: revise ? "revise" : "create",
    queuePos: phase === "queued" ? (job.queuePosition ?? 0) : 0,
    err: job.error?.code ?? null,
    errMessage: job.error?.message ?? "",
    ver: job.version,
    history,
    pendingFix,
  };
}

/** 承認（登録）できるか。生成・修正中は不可。タイトル・本文が空でないこと。 */
export function canApprove(state: PlanState): boolean {
  return (
    derivePlanView(state.job).phase === "review" &&
    !!state.title.trim() &&
    !!state.body.trim()
  );
}

/** 計画確認欄を表示するか（修正中・修正失敗時も直前の計画を残して見せる）。 */
export function showReview(view: PlanView): boolean {
  if (view.ver === 0) return false;
  return (
    view.phase === "review" ||
    ((view.phase === "queued" ||
      view.phase === "generating" ||
      view.phase === "error") &&
      view.op === "revise")
  );
}

/** 一覧表示用の短い状態名（inbox・新規タスク由来の未承認計画）。 */
export type PlanBadge = "queued" | "running" | "review" | "failed";

export function planBadge(job: PlanJob): PlanBadge {
  switch (job.status) {
    case "queued":
      return "queued";
    case "running":
      return "running";
    case "failed":
      return "failed";
    case "succeeded":
      return "review";
  }
}

/** 実行中（キュー待ち・作成中）のジョブがあるか。ポーリングの要否判断に使う。 */
export function hasActivePlan(jobs: readonly PlanJob[]): boolean {
  return jobs.some((j) => j.status === "queued" || j.status === "running");
}
