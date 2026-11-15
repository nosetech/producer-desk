"use client";

import {
  useEffect,
  useState,
  type Dispatch as ReactDispatch,
  type ReactNode,
} from "react";
import {
  deleteIssuePlan,
  patchIssuePlan,
  postIssuePlan,
  postReviseIssuePlan,
  postRetryIssuePlan,
  type PlanJob,
} from "@/lib/api";
import { MODEL_DEFAULT } from "@/lib/modelDirective";
import {
  canApprove,
  derivePlanView,
  showReview,
  type PlanAction,
  type PlanErrorKind,
  type PlanState,
} from "@/lib/planFlow";
import { formatAbsoluteTime } from "@/lib/issueList";
import type { Dispatch } from "@/lib/types";
import PlanBadge from "./PlanBadge";
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
    title: "計画の作成に失敗しました",
    desc: "計画の作成中にエラーが発生しました。再試行するか、ログを確認してください。",
    code: "PLAN_FAILED",
  },
  interrupted: {
    title: "計画の作成が中断されました",
    desc: "オーケストレータの再起動により処理が中断されました。再試行すると最初からやり直します。",
    code: "INTERRUPTED",
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
  jobs,
  loaded,
  variant = "compose",
  inboxIssueNumber,
  modelRow,
  refresh,
  onRequested,
  onApprove,
  onClose,
  onError,
}: {
  repo: string;
  /** モデル選択値（`MODEL_DEFAULT`なら既定のまま）。 */
  model: string;
  state: PlanState;
  dispatch: ReactDispatch<PlanAction>;
  /** プロジェクトの計画ジョブ一覧（ポーリング結果）。選択中のジョブの最新状態を反映する。 */
  jobs: PlanJob[];
  loaded: boolean;
  /**
   * compose: 新規作成パネル（依頼→パネルを閉じる、未承認の計画を一覧から選べる）。
   * inline: inbox一覧の行内パネル（既存のジョブの確認のみ）。
   */
  variant?: "compose" | "inline";
  /** inbox項目由来の計画のとき、その項目のissue番号。 */
  inboxIssueNumber?: number;
  modelRow?: ReactNode;
  /** 操作直後にジョブ一覧を再取得する。 */
  refresh: () => Promise<void>;
  /** 計画を依頼した（compose）。パネルを閉じてトーストを出すのは呼び出し側。 */
  onRequested?: () => void;
  /** 承認（登録）。成功後の計画ジョブ削除は呼び出し側がジョブIDで行う。 */
  onApprove: (
    dispatch: Dispatch,
    title: string,
    body: string,
    jobId: string,
  ) => void;
  /** 計画を残したままパネルを閉じる。 */
  onClose: () => void;
  onError: (message: string) => void;
}) {
  const [pending, setPending] = useState(false);
  const inline = variant === "inline";
  const job = state.job;
  const view = derivePlanView(job);

  // ポーリング結果から、選択中のジョブの最新状態（キュー順位・結果・破棄）を反映する。
  useEffect(() => {
    if (!job || !loaded) return;
    const latest = jobs.find((j) => j.id === job.id) ?? null;
    if (latest !== job) dispatch({ type: "sync", job: latest });
  }, [jobs, loaded, job, dispatch]);

  // 同じプロジェクトの、新規タスク由来の未承認の計画（新規作成を開いたとき復元する）。
  const restorable = inline
    ? []
    : jobs.filter((j) => j.inboxIssueNumber === null);

  async function act(fn: () => Promise<void>) {
    setPending(true);
    try {
      await fn();
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  }

  /** 直接編集した内容を保存する（閉じる・一覧へ戻るときに失わないため）。 */
  async function saveEdits() {
    if (
      !job ||
      view.phase !== "review" ||
      !job.result ||
      (job.result.title === state.title && job.result.body === state.body)
    )
      return;
    await patchIssuePlan(repo, job.id, {
      title: state.title,
      body: state.body,
    });
  }

  function request() {
    void act(async () => {
      const created = await postIssuePlan(repo, {
        request: state.want.trim(),
        ...(model !== MODEL_DEFAULT ? { model } : {}),
        ...(inboxIssueNumber !== undefined ? { inboxIssueNumber } : {}),
      });
      void created;
      await refresh();
      onRequested?.();
    });
  }

  function sendFix() {
    if (!job) return;
    const instruction = state.fix.trim();
    if (!instruction) return;
    void act(async () => {
      await saveEdits().catch(() => {});
      await postReviseIssuePlan(
        repo,
        job.id,
        instruction,
        model !== MODEL_DEFAULT ? model : undefined,
      );
      dispatch({ type: "revised" });
      await refresh();
    });
  }

  function retry() {
    if (!job) return;
    void act(async () => {
      await postRetryIssuePlan(repo, job.id);
      await refresh();
    });
  }

  /** 失敗からの「直前の計画に戻る」（修正の失敗）／「計画を破棄」（初回の失敗）。 */
  function back() {
    if (!job) return;
    void act(async () => {
      if (view.op === "revise" && job.result) {
        await patchIssuePlan(repo, job.id, {
          title: job.result.title,
          body: job.result.body,
        });
        await refresh();
      } else {
        await deleteIssuePlan(repo, job.id);
        dispatch({ type: "reset" });
        await refresh();
      }
    });
  }

  function discard() {
    if (!job) return;
    void act(async () => {
      await deleteIssuePlan(repo, job.id);
      dispatch({ type: "reset", want: inline ? undefined : state.want });
      await refresh();
      if (inline) onClose();
    });
  }

  function close() {
    void act(async () => {
      await saveEdits().catch(() => {});
      await refresh();
      onClose();
    });
  }

  function approve(dispatchKind: Dispatch) {
    if (!job) return;
    onApprove(dispatchKind, state.title.trim(), state.body.trim(), job.id);
  }

  const ph = view.phase;
  const busy = ph === "queued" || ph === "generating";
  const queued = ph === "queued";
  const revise = view.op === "revise";
  const review = showReview(view);
  const locked = ph !== "review" || pending;
  const hasFix = !!state.fix.trim();
  const approvable = canApprove(state) && !pending;
  const err = view.err ? ERRORS[view.err] : null;
  const wantLocked = ph !== "input" || inline;

  return (
    <div className={styles.stack}>
      {!job && restorable.length > 0 && (
        <div role="region" aria-label="未承認の計画" className={styles.pendBox}>
          <div className={styles.pendHead}>
            <span className={styles.label}>未承認の計画</span>
            <span className={styles.pendCount}>{restorable.length}</span>
            <span className={styles.spacer} />
            <span className={styles.sub}>選ぶと内容を確認できます</span>
          </div>
          {restorable.map((j) => (
            <button
              key={j.id}
              type="button"
              className={styles.pendRow}
              aria-label={`${repo} の計画（${j.status}）を開く`}
              onClick={() => {
                dispatch({ type: "edit", patch: { want: j.request } });
                dispatch({ type: "sync", job: j });
              }}
            >
              <PlanBadge job={j} />
              <span className={styles.pendText}>
                <span className={styles.pendTitle}>
                  {j.result ? j.result.title : j.request}
                </span>
                <span className={styles.pendMeta}>
                  {repo} · {formatAbsoluteTime(j.createdAt)}に依頼
                </span>
              </span>
              {j.version > 0 && (
                <span className={styles.ver}>v{j.version}</span>
              )}
            </button>
          ))}
          <span className={styles.pendNote}>
            計画はバックグラウンドで作成されます。新しく依頼するときは下に入力してください。
          </span>
        </div>
      )}
      {job && !inline && (
        <div className={styles.selBar}>
          <button
            type="button"
            className={styles.ghostBtn}
            disabled={pending}
            onClick={() => {
              void act(async () => {
                await saveEdits().catch(() => {});
                await refresh();
                dispatch({ type: "reset", want: "" });
              });
            }}
          >
            未承認の計画へ
          </button>
          <PlanBadge job={job} />
        </div>
      )}
      {inboxIssueNumber !== undefined && !inline && !job && (
        <span className={styles.pendNote}>
          inbox {repo} #{inboxIssueNumber}{" "}
          の計画を依頼します。承認するとこのinbox項目が status:todo
          に昇格します。
        </span>
      )}
      <div>
        <div className={styles.labelRow}>
          <span className={styles.label}>やりたいこと</span>
          {ph !== "input" && (
            <span className={styles.sub}>計画の作成に使用した内容</span>
          )}
        </div>
        {!inline && modelRow}
        <textarea
          className={`${styles.field} ${styles.want} ${wantLocked ? styles.wantLocked : ""}`}
          placeholder="やりたいことを自由に書いてください。AIがissueのタイトルと本文（背景・やること・完了条件）を下書きします。（例: 請求書の合計が明細と合わないときに気づけるようにしたい）"
          value={state.want}
          onChange={(e) =>
            dispatch({ type: "edit", patch: { want: e.target.value } })
          }
          disabled={wantLocked}
        />
      </div>

      {ph === "input" && !inline && (
        <div className={styles.genRow}>
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={request}
            disabled={!state.want.trim() || pending}
          >
            {sparkle}
            計画を依頼
          </button>
          <span className={styles.genNote}>
            依頼するとバックグラウンドで作成され、完了するとSlackに通知します。承認するまでissueは作成されません。
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
              ? `待機中 · キュー${view.queuePos}番目`
              : revise
                ? "修正を反映中"
                : "計画を作成中"}
          </span>
          <Stage
            label={
              queued
                ? `キューで待機中（${view.queuePos}番目）`
                : false
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
                ? `「${view.pendingFix}」を反映しています。直前の計画は下に残っています。`
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
                  view.ver > 0 &&
                  ` 直前の計画（v${view.ver}）はそのまま残っています。`}
              </span>
              <span className={styles.errorCode}>
                {err.code}
                {view.errMessage ? ` · ${view.errMessage}` : ""}
              </span>
            </div>
          </div>
          <div className={styles.btnRow}>
            <button type="button" className={styles.retryBtn} onClick={retry}>
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
              disabled={pending}
              onClick={back}
            >
              {revise && view.ver > 0 ? "直前の計画に戻る" : "計画を破棄"}
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
              <span className={styles.ver}>v{view.ver}</span>
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
                {view.history.length > 0 && (
                  <span className={styles.sub}>
                    修正 {view.history.length}回
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
                      if (!locked && hasFix) sendFix();
                    }
                  }}
                  disabled={locked}
                  placeholder="例: 許容誤差は設定ファイルで変えられるようにして"
                  aria-label="AIへの修正指示"
                />
                <button
                  type="button"
                  className={styles.fixBtn}
                  onClick={sendFix}
                  disabled={locked || !hasFix}
                  aria-label="修正を指示"
                  title="修正を指示（Enter）"
                >
                  {sparkle}
                  <span>修正を指示</span>
                </button>
              </div>
              {view.history.length > 0 && (
                <div className={styles.history}>
                  {view.history.map((t, i) => (
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
              {!inline && (
                <button
                  type="button"
                  className={styles.primaryBtn}
                  disabled={!approvable}
                  onClick={() => approve("immediate")}
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
              )}
              <button
                type="button"
                className={inline ? styles.primaryBtn : styles.laterBtn}
                disabled={!approvable}
                onClick={() => approve("queued")}
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
                {inline
                  ? "承認して登録（status:todo）"
                  : "承認して登録 · あとで着手（todo）"}
              </button>
            </div>
            <div className={styles.actionRow} style={{ gap: 8 }}>
              <button
                type="button"
                className={styles.ghostBtn}
                disabled={busy || pending}
                onClick={discard}
                title="計画を破棄します"
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
                破棄
              </button>
              <button
                type="button"
                className={styles.ghostBtn}
                disabled={pending}
                onClick={close}
                title="計画は残したまま閉じます"
              >
                閉じる
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
