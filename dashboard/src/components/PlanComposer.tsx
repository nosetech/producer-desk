"use client";

import {
  useEffect,
  useRef,
  type Dispatch as ReactDispatch,
  type ReactNode,
} from "react";
import { postIssuePlan, PlanApiError } from "@/lib/api";
import { MODEL_DEFAULT } from "@/lib/modelDirective";
import {
  canApprove,
  showReview,
  type PlanAction,
  type PlanErrorKind,
  type PlanOp,
  type PlanState,
} from "@/lib/planFlow";
import { useStageProgress } from "@/lib/stageProgress";
import type { Dispatch } from "@/lib/types";
import styles from "./PlanComposer.module.css";

const ERRORS: Record<
  PlanErrorKind,
  { title: string; desc: string; code: string }
> = {
  parse: {
    title: "AIの出力を解釈できませんでした",
    desc: "計画（タイトル・本文）の形式を読み取れませんでした。もう一度作成すると解決することがあります。",
    code: "PLAN_PARSE_ERROR",
  },
  timeout: {
    title: "計画の作成がタイムアウトしました",
    desc: "時間内に応答がありませんでした。時間をおいて再試行してください。",
    code: "TIMEOUT",
  },
  limit: {
    title: "利用リミットに達しました",
    desc: "このモデルの利用上限に達したため、計画を作成できません。リセット後に再試行するか、モデルを切り替えてください。",
    code: "RATE_LIMIT · 429",
  },
  failed: {
    title: "計画を作成できませんでした",
    desc: "計画の作成中にエラーが発生しました。もう一度お試しください。",
    code: "PLAN_FAILED",
  },
};

const sparkle = (
  <svg
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ flex: "none" }}
  >
    <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9Z" />
    <path d="M19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7Z" />
  </svg>
);

function Spinner() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 42 42"
      className={styles.spin}
      aria-hidden
    >
      <circle
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        opacity=".28"
      />
      <circle
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray="34 200"
      />
    </svg>
  );
}

type StageState = "done" | "waiting" | "active" | "pending";

function StageIcon({ state }: { state: StageState }) {
  if (state === "done")
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="var(--accent-green)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ flex: "none" }}
      >
        <path d="M20 6 9 17l-5-5" />
      </svg>
    );
  return (
    <span
      className={styles.stageIcon}
      style={state === "waiting" ? { color: "var(--accent-gray)" } : undefined}
    >
      {state === "waiting" ? (
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </svg>
      ) : (
        <span
          className={state === "active" ? styles.dotActive : styles.dotPending}
        />
      )}
    </span>
  );
}

function Stage({
  label,
  note,
  state,
}: {
  label: string;
  note: string;
  state: StageState;
}) {
  const strong = state === "active" || state === "waiting";
  return (
    <div className={styles.stageRow}>
      <StageIcon state={state} />
      <span
        className={styles.stageLabel}
        style={{
          fontWeight: strong ? 600 : 400,
          color:
            state === "pending"
              ? "var(--text-tertiary)"
              : state === "done"
                ? "var(--text-secondary)"
                : "var(--text-primary)",
        }}
      >
        {label}
      </span>
      <span className={styles.stageLine} />
      <span className={styles.stageNote}>{note}</span>
    </div>
  );
}

export function PlanModeToggle({
  mode,
  busy,
  onChange,
}: {
  mode: "manual" | "plan";
  busy: boolean;
  onChange: (mode: "manual" | "plan") => void;
}) {
  const cls = (on: boolean) => `${styles.seg} ${on ? styles.segOn : ""}`;
  return (
    <div role="tablist" aria-label="作成方法" className={styles.segWrap}>
      <button
        type="button"
        role="tab"
        aria-selected={mode === "manual"}
        className={cls(mode === "manual")}
        disabled={busy}
        onClick={() => onChange("manual")}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.1"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ flex: "none" }}
        >
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
        </svg>
        自分で書く
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={mode === "plan"}
        className={cls(mode === "plan")}
        disabled={busy}
        onClick={() => onChange("plan")}
      >
        {sparkle}
        AIに計画してもらう
      </button>
    </div>
  );
}

export default function PlanComposer({
  repo,
  model,
  state,
  dispatch,
  modelRow,
  onApprove,
  onCancel,
}: {
  repo: string;
  /** モデル選択値（`MODEL_DEFAULT`なら既定のまま）。 */
  model: string;
  state: PlanState;
  dispatch: ReactDispatch<PlanAction>;
  modelRow: ReactNode;
  onApprove: (dispatch: Dispatch, title: string, body: string) => void;
  onCancel: () => void;
}) {
  const progress = useStageProgress();
  const runId = useRef(0);
  const stateRef = useRef(state);
  stateRef.current = state;

  // 実行中の進捗（キュー順位・作成中）をサーバのポーリング結果から反映する。
  useEffect(() => {
    dispatch({ type: "stage", stage: progress.polledStage });
  }, [progress.polledStage, dispatch]);

  // アンマウント（パネルを閉じた）後の結果は捨てる。
  useEffect(() => {
    return () => {
      runId.current += 1;
    };
  }, []);

  function run(op: PlanOp) {
    const s = stateRef.current;
    const instruction =
      op === "revise" ? s.pendingFix || s.fix.trim() : undefined;
    const id = ++runId.current;
    // pendingFixはreducerがfixから取り出す。先にstartしてから通信する。
    dispatch({ type: "start", op });
    const progressId = progress.start();
    postIssuePlan(
      repo,
      {
        request: s.want.trim(),
        ...(op === "revise"
          ? { previousPlan: { title: s.title, body: s.body }, instruction }
          : {}),
        ...(model !== MODEL_DEFAULT ? { model } : {}),
      },
      progressId,
    )
      .then((plan) => {
        if (id !== runId.current) return;
        dispatch({ type: "succeeded", title: plan.title, body: plan.body });
      })
      .catch((e: unknown) => {
        if (id !== runId.current) return;
        dispatch({
          type: "failed",
          kind: e instanceof PlanApiError ? e.kind : "failed",
          message: e instanceof Error ? e.message : String(e),
        });
      })
      .finally(() => {
        if (id === runId.current) progress.stop();
      });
  }

  const ph = state.phase;
  const busy = ph === "queued" || ph === "generating";
  const queued = ph === "queued";
  const revise = state.op === "revise";
  const review = showReview(state);
  const locked = ph !== "review";
  const hasFix = !!state.fix.trim();
  const approvable = canApprove(state);
  const err = state.err ? ERRORS[state.err] : null;

  return (
    <div className={styles.stack}>
      <div>
        <div className={styles.labelRow}>
          <span className={styles.label}>やりたいこと</span>
          {ph !== "input" && (
            <span className={styles.sub}>計画の作成に使用した内容</span>
          )}
        </div>
        {modelRow}
        <textarea
          className={`${styles.field} ${styles.want} ${ph !== "input" ? styles.wantLocked : ""}`}
          placeholder="やりたいことを自由に書いてください。AIがissueのタイトルと本文（背景・やること・完了条件）を下書きします。（例: 請求書の合計が明細と合わないときに気づけるようにしたい）"
          value={state.want}
          onChange={(e) =>
            dispatch({ type: "edit", patch: { want: e.target.value } })
          }
          disabled={ph !== "input"}
        />
      </div>

      {ph === "input" && (
        <div className={styles.genRow}>
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={() => run("create")}
            disabled={!state.want.trim()}
          >
            {sparkle}
            計画を作成
          </button>
          <span className={styles.genNote}>
            作成された計画を確認・修正してから登録します。承認するまでissueは作成されません。
          </span>
        </div>
      )}

      {busy && (
        <div role="status" aria-live="polite" className={styles.busyBox}>
          <span className={`${styles.chip} ${queued ? styles.chipQueued : ""}`}>
            {queued ? (
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ flex: "none" }}
              >
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
              </svg>
            ) : (
              <Spinner />
            )}
            {queued
              ? `待機中 · キュー${state.queuePos}番目`
              : revise
                ? "修正を反映中"
                : "計画を作成中"}
          </span>
          <Stage
            label={
              queued
                ? `キューで待機中（${state.queuePos}番目）`
                : state.wasQueued
                  ? "キューで待機"
                  : "キュー待ちなし"
            }
            note="queue"
            state={queued ? "waiting" : "done"}
          />
          <Stage
            label={revise ? "修正を反映中" : "計画を作成中"}
            note={model === MODEL_DEFAULT ? "既定のモデル" : model}
            state={queued ? "pending" : "active"}
          />
          <Stage
            label={revise ? "修正した計画を表示" : "計画を表示"}
            note="draft"
            state="pending"
          />
          <span className={styles.note}>
            {queued
              ? `${repo} で実行中の作業が終わると、自動で計画の作成を始めます。`
              : revise
                ? `「${state.pendingFix}」を反映しています。直前の計画は下に残っています。`
                : "AIがタイトルと本文を下書きしています。完了まで入力はできません。"}
          </span>
        </div>
      )}

      {ph === "error" && err && (
        <div role="alert" className={styles.errorBox}>
          <div className={styles.errorHead}>
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--warn)"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ flex: "none", marginTop: 1 }}
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8v4M12 16h.01" />
            </svg>
            <div className={styles.errorText}>
              <span className={styles.errorTitle}>{err.title}</span>
              <span className={styles.errorDesc}>
                {err.desc}
                {revise &&
                  state.ver > 0 &&
                  ` 直前の計画（v${state.ver}）はそのまま残っています。`}
              </span>
              <span className={styles.errorCode}>
                {err.code}
                {state.errMessage ? ` · ${state.errMessage}` : ""}
              </span>
            </div>
          </div>
          <div className={styles.btnRow}>
            <button
              type="button"
              className={styles.retryBtn}
              onClick={() => run(state.op)}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.3"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ flex: "none" }}
              >
                <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
                <path d="M3 3v5h5" />
              </svg>
              再試行
            </button>
            <button
              type="button"
              className={styles.ghostBtn}
              onClick={() => dispatch({ type: "back" })}
            >
              {revise && state.ver > 0 ? "直前の計画に戻る" : "入力に戻る"}
            </button>
          </div>
        </div>
      )}

      {review && (
        <>
          <div
            className={`${styles.reviewBox} ${locked ? styles.reviewLocked : ""}`}
          >
            <div className={styles.reviewHead}>
              <span className={styles.label}>計画（下書き）</span>
              <span className={styles.ver}>v{state.ver}</span>
              <span className={styles.spacer} />
              <span className={styles.sub}>
                {locked
                  ? "修正中は編集できません"
                  : "AIが作成 · 直接編集できます"}
              </span>
            </div>
            <div>
              <div className={styles.labelRow}>
                <span className={styles.label}>タイトル</span>
              </div>
              <input
                className={`${styles.field} ${styles.title}`}
                value={state.title}
                onChange={(e) =>
                  dispatch({ type: "edit", patch: { title: e.target.value } })
                }
                disabled={locked}
                aria-label="issueのタイトル"
              />
            </div>
            <div>
              <div className={styles.labelRow}>
                <span className={styles.label}>本文</span>
              </div>
              <textarea
                className={`${styles.field} ${styles.bodyField}`}
                value={state.body}
                onChange={(e) =>
                  dispatch({ type: "edit", patch: { body: e.target.value } })
                }
                disabled={locked}
                aria-label="issueの本文"
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className={styles.labelRow} style={{ marginBottom: 0 }}>
                <span className={styles.label}>AIに修正を指示</span>
                {state.history.length > 0 && (
                  <span className={styles.sub}>
                    修正 {state.history.length}回
                  </span>
                )}
              </div>
              <div className={styles.fixRow}>
                <input
                  className={`${styles.field} ${styles.fixInput}`}
                  value={state.fix}
                  onChange={(e) =>
                    dispatch({ type: "edit", patch: { fix: e.target.value } })
                  }
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      !e.nativeEvent.isComposing &&
                      !e.shiftKey
                    ) {
                      e.preventDefault();
                      if (!locked && hasFix) run("revise");
                    }
                  }}
                  disabled={locked}
                  placeholder="例: 許容誤差は設定ファイルで変えられるようにして"
                  aria-label="AIへの修正指示"
                />
                <button
                  type="button"
                  className={styles.fixBtn}
                  onClick={() => run("revise")}
                  disabled={locked || !hasFix}
                  aria-label="修正を指示"
                  title="修正を指示（Enter）"
                >
                  {sparkle}
                  <span>修正を指示</span>
                </button>
              </div>
              {state.history.length > 0 && (
                <div className={styles.history}>
                  {state.history.map((t, i) => (
                    <div key={i} className={styles.historyItem}>
                      <span className={styles.historyNum}>{i + 1}.</span>
                      <span className={styles.historyText}>{t}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className={styles.approveNote}>
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ flex: "none", marginTop: 1 }}
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M12 16v-4M12 8h.01" />
            </svg>
            <span>
              <strong>承認するまでissueは作成されません。</strong>
              内容を確認・修正してから登録してください。
            </span>
          </div>
          <div className={styles.actions}>
            <div className={styles.actionRow}>
              <button
                type="button"
                className={styles.primaryBtn}
                disabled={!approvable}
                onClick={() =>
                  onApprove("immediate", state.title.trim(), state.body.trim())
                }
              >
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{ flex: "none" }}
                >
                  <path d="M20 6 9 17l-5-5" />
                </svg>
                承認して登録 · 今すぐ着手
              </button>
              <button
                type="button"
                className={styles.laterBtn}
                disabled={!approvable}
                onClick={() =>
                  onApprove("queued", state.title.trim(), state.body.trim())
                }
              >
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{ flex: "none" }}
                >
                  <rect x="3" y="5" width="18" height="16" rx="2" />
                  <path d="M16 3v4M8 3v4M3 11h18M9 15l2 2 4-4" />
                </svg>
                承認して登録 · あとで着手（todo）
              </button>
            </div>
            <div className={styles.actionRow} style={{ gap: 8 }}>
              <button
                type="button"
                className={styles.ghostBtn}
                disabled={busy}
                onClick={() => dispatch({ type: "redo" })}
                title="計画を破棄して、やりたいことの入力に戻ります"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{ flex: "none" }}
                >
                  <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
                  <path d="M3 3v5h5" />
                </svg>
                やり直す
              </button>
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={onCancel}
                title="計画を破棄して閉じます"
              >
                キャンセル
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
