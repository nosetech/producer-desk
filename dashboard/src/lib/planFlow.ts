// 「AIに計画してもらう」（issue #287）の状態遷移。
// 生成（入力→待機中→作成中）→確認（直接編集・AIへの修正指示を繰り返す）→承認、の
// 流れを純粋関数のreducerで表す（UI・通信から切り離してテストできるようにする）。

export type PlanPhase = "input" | "queued" | "generating" | "review" | "error";
export type PlanOp = "create" | "revise";
export type PlanErrorKind = "parse" | "timeout" | "limit" | "failed";

export interface PlanState {
  phase: PlanPhase;
  op: PlanOp;
  want: string;
  title: string;
  body: string;
  fix: string;
  /** 送信済みでAIが反映中の修正指示。 */
  pendingFix: string;
  /** 計画の版（0=未作成）。 */
  ver: number;
  /** 反映済みの修正指示の履歴。 */
  history: string[];
  queuePos: number;
  wasQueued: boolean;
  err: PlanErrorKind | null;
  errMessage: string;
}

export function initialPlanState(want = ""): PlanState {
  return {
    phase: "input",
    op: "create",
    want,
    title: "",
    body: "",
    fix: "",
    pendingFix: "",
    ver: 0,
    history: [],
    queuePos: 0,
    wasQueued: false,
    err: null,
    errMessage: "",
  };
}

export type PlanAction =
  | {
      type: "edit";
      patch: Partial<Pick<PlanState, "want" | "title" | "body" | "fix">>;
    }
  | { type: "start"; op: PlanOp }
  | { type: "stage"; stage: string | null }
  | { type: "succeeded"; title: string; body: string }
  | { type: "failed"; kind: PlanErrorKind; message: string }
  | { type: "back" }
  | { type: "redo" };

const QUEUED_PREFIX = "plan_queued:";
const RUNNING = "plan_running";

/** サーバの進捗段階（`plan_queued:<順位>` / `plan_running`）を解釈する。 */
export function parsePlanStage(
  stage: string | null,
): { kind: "queued"; pos: number } | { kind: "running" } | null {
  if (!stage) return null;
  if (stage === RUNNING) return { kind: "running" };
  if (stage.startsWith(QUEUED_PREFIX)) {
    const pos = Number(stage.slice(QUEUED_PREFIX.length));
    if (Number.isInteger(pos) && pos > 0) return { kind: "queued", pos };
  }
  return null;
}

export function planReducer(state: PlanState, action: PlanAction): PlanState {
  switch (action.type) {
    case "edit":
      return { ...state, ...action.patch };
    case "start": {
      // 修正指示は送信時に入力欄から取り出し、反映中は「直前の計画」を残す。
      const revise = action.op === "revise";
      return {
        ...state,
        op: action.op,
        phase: "generating",
        err: null,
        errMessage: "",
        queuePos: 0,
        wasQueued: false,
        pendingFix: revise ? state.pendingFix || state.fix.trim() : "",
        fix: revise ? "" : state.fix,
      };
    }
    case "stage": {
      if (state.phase !== "queued" && state.phase !== "generating")
        return state;
      const parsed = parsePlanStage(action.stage);
      if (!parsed) return state;
      if (parsed.kind === "queued")
        return {
          ...state,
          phase: "queued",
          queuePos: parsed.pos,
          wasQueued: true,
        };
      return { ...state, phase: "generating", queuePos: 0 };
    }
    case "succeeded": {
      const revise = state.op === "revise";
      return {
        ...state,
        phase: "review",
        title: action.title,
        body: action.body,
        ver: revise ? state.ver + 1 : 1,
        history: revise ? [...state.history, state.pendingFix] : [],
        pendingFix: "",
        err: null,
        errMessage: "",
      };
    }
    case "failed":
      return {
        ...state,
        phase: "error",
        err: action.kind,
        errMessage: action.message,
      };
    case "back":
      // 修正の失敗は直前の計画へ、作成の失敗は入力へ戻る。
      if (state.op === "revise" && state.ver > 0)
        return {
          ...state,
          phase: "review",
          fix: state.pendingFix,
          pendingFix: "",
          err: null,
          errMessage: "",
        };
      return { ...state, phase: "input", err: null, errMessage: "" };
    case "redo":
      return initialPlanState(state.want);
  }
}

/** 承認（登録）できるか。生成・修正中は不可。タイトル・本文が空でないこと。 */
export function canApprove(state: PlanState): boolean {
  return (
    state.phase === "review" && !!state.title.trim() && !!state.body.trim()
  );
}

/** 計画確認欄を表示するか（修正中・修正失敗時も直前の計画を残して見せる）。 */
export function showReview(state: PlanState): boolean {
  if (state.ver === 0) return false;
  return (
    state.phase === "review" ||
    ((state.phase === "queued" ||
      state.phase === "generating" ||
      state.phase === "error") &&
      state.op === "revise")
  );
}
