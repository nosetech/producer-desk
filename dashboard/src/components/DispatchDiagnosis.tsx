"use client";

import { useEffect, useRef, useState } from "react";
import { fetchDispatchStatus, postRedispatch } from "@/lib/api";
import { DIAG_META, TONE_VARS } from "@/lib/dispatchDiagnosis";
import type { StageDef } from "@/lib/stageProgress";
import { formatRelativeTime } from "@/lib/time";
import type { DispatchStatus } from "@/lib/types";
import { useApp } from "./AppContext";
import { SpinnerIcon } from "./StageProgress";
import styles from "./DispatchDiagnosis.module.css";

// orchestrator/orchestrator/dispatch_status.py の handle_redispatch が通知する
// on_stage（apply_instruction の label/dispatch と、再実行記録コメントの comment）と対応する。
const RERUN_STAGES: StageDef[] = [
  { key: "label", label: "ラベルを更新", note: "label" },
  { key: "dispatch", label: "エージェントへ引き渡し", note: "queue" },
  { key: "comment", label: "再実行を記録", note: "POST comment" },
];

const Svg = ({
  children,
  size = 14,
}: {
  children: React.ReactNode;
  size?: number;
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ flex: "none" }}
    aria-hidden="true"
  >
    {children}
  </svg>
);

function StateIcon({ state }: { state: DispatchStatus["state"] }) {
  switch (state) {
    case "running":
      return <SpinnerIcon />;
    case "queued":
      return (
        <Svg size={15}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </Svg>
      );
    case "completed":
      return (
        <Svg size={15}>
          <circle cx="12" cy="12" r="9" />
          <path d="m8 12 3 3 5-6" />
        </Svg>
      );
    case "not_dispatched":
      return (
        <Svg size={15}>
          <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
          <path d="M12 8v4M12 15.5h.01" />
        </Svg>
      );
    case "orphaned_in_progress":
      return (
        <Svg size={15}>
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
          <path d="M12 9v4M12 17h.01" />
        </Svg>
      );
    default:
      return (
        <Svg size={15}>
          <circle cx="12" cy="12" r="9" />
          <path d="m5.7 5.7 12.6 12.6" />
        </Svg>
      );
  }
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.note}>
      <Svg>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 16v-4M12 8h.01" />
      </Svg>
      <span>{children}</span>
    </div>
  );
}

/**
 * issueの「状態をチェック」操作と診断結果パネル（issue #215）。診断はオーケストレータの
 * dispatch-status APIで行い、再実行は他の操作と同じバックグラウンドジョブとして実行する
 * （別プロジェクトの操作をブロックしない）。
 */
export default function DispatchDiagnosis({
  repo,
  number,
  title,
  busy,
}: {
  repo: string;
  number: number;
  title: string;
  busy: boolean;
}) {
  const { startJob } = useApp();
  const [open, setOpen] = useState(false);
  const [checking, setChecking] = useState(false);
  const [status, setStatus] = useState<DispatchStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const seq = useRef(0);

  // 再実行ジョブの開始中・失敗中は、ジョブの進捗表示に委ねて診断パネルを隠す。
  useEffect(() => {
    if (busy) {
      seq.current++;
      setOpen(false);
      setConfirming(false);
    }
  }, [busy]);

  function check() {
    const mySeq = ++seq.current;
    setOpen(true);
    setChecking(true);
    setConfirming(false);
    setError(null);
    fetchDispatchStatus(repo, number)
      .then((s) => {
        if (mySeq !== seq.current) return;
        setStatus(s);
      })
      .catch((e) => {
        if (mySeq !== seq.current) return;
        setStatus(null);
        setError(e instanceof Error ? e.message : "状態を確認できませんでした");
      })
      .finally(() => {
        if (mySeq === seq.current) setChecking(false);
      });
  }

  function close() {
    seq.current++;
    setOpen(false);
    setConfirming(false);
  }

  function rerun() {
    const repoName = repo.split("/")[1];
    setOpen(false);
    setConfirming(false);
    startJob({
      kind: "rerun",
      repo,
      number,
      title,
      stages: RERUN_STAGES,
      exec: (progressId) => postRedispatch(repo, number, progressId),
      successMessage: `${repoName} #${number} の指示を再実行しました。`,
    });
  }

  const meta = status ? DIAG_META[status.state] : null;
  const tone = meta ? TONE_VARS[meta.tone] : null;
  const emphasized =
    status?.state === "not_dispatched" ||
    status?.state === "orphaned_in_progress";
  const active = status?.state === "running" || status?.state === "queued";
  const canRerun = !!status?.redispatchable && !!status.pending_message;
  const noComment =
    (status?.state === "not_dispatched" ||
      status?.state === "orphaned_in_progress") &&
    !canRerun;

  return (
    <div className={styles.root}>
      <div className={styles.triggerRow}>
        <button
          type="button"
          className={styles.linkBtn}
          onClick={check}
          disabled={busy || checking}
          title="オーケストレータでの処理状態を確認"
          aria-expanded={open}
        >
          <Svg size={13}>
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </Svg>
          状態をチェック
        </button>
      </div>
      {open && (
        <div
          role="region"
          aria-label="状態チェックの結果"
          aria-live="polite"
          className={styles.box}
          style={
            !checking && emphasized && tone
              ? { borderColor: `var(${tone.color})` }
              : undefined
          }
        >
          {checking && (
            <div className={styles.checking}>
              <SpinnerIcon />
              <span className={styles.checkingText}>状態を確認中…</span>
              <span className={styles.spacer} />
              <span className={styles.target}>
                GET {repo} #{number}
              </span>
            </div>
          )}
          {!checking && error && (
            <>
              <div className={styles.resultHead}>
                <div className={styles.resultBody}>
                  <span
                    className={styles.label}
                    style={{ color: "var(--warn)" }}
                  >
                    状態を確認できませんでした
                  </span>
                  <span className={styles.desc}>{error}</span>
                </div>
                <button
                  type="button"
                  className={styles.closeBtn}
                  onClick={close}
                  title="閉じる"
                  aria-label="状態チェックの結果を閉じる"
                >
                  <Svg size={13}>
                    <path d="M18 6 6 18M6 6l12 12" />
                  </Svg>
                </button>
              </div>
              <div className={styles.btnRow}>
                <button
                  type="button"
                  className={styles.rerunBtn}
                  onClick={check}
                >
                  再試行
                </button>
              </div>
            </>
          )}
          {!checking && status && meta && tone && (
            <>
              <div className={styles.resultHead}>
                <span
                  className={`${styles.iconWrap} ${status.state === "not_managed" ? styles.iconWrapDashed : ""}`}
                  style={{
                    background: `var(${tone.bg})`,
                    color: `var(${tone.color})`,
                  }}
                >
                  <StateIcon state={status.state} />
                </span>
                <div className={styles.resultBody}>
                  <div className={styles.labelRow}>
                    <span
                      className={styles.label}
                      style={{ color: `var(${tone.color})` }}
                    >
                      {meta.label}
                    </span>
                    {status.pending_comment_created_at && (
                      <span className={styles.meta}>
                        最終指示{" "}
                        {formatRelativeTime(status.pending_comment_created_at)}
                      </span>
                    )}
                  </div>
                  <span className={styles.desc}>{meta.desc}</span>
                </div>
                <button
                  type="button"
                  className={styles.closeBtn}
                  onClick={close}
                  title="閉じる"
                  aria-label="状態チェックの結果を閉じる"
                >
                  <Svg size={13}>
                    <path d="M18 6 6 18M6 6l12 12" />
                  </Svg>
                </button>
              </div>
              {active && <Note>すでに実行中のため再実行できません。</Note>}
              {noComment && (
                <Note>
                  未処理の指示コメントがありません。再開するには、issueに指示を返信してください。
                </Note>
              )}
              {canRerun && !confirming && (
                <div className={styles.btnRow}>
                  <button
                    type="button"
                    className={styles.rerunBtn}
                    onClick={() => setConfirming(true)}
                  >
                    <Svg>
                      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
                      <path d="M3 3v5h5" />
                    </Svg>
                    再実行…
                  </button>
                </div>
              )}
              {canRerun && confirming && (
                <div className={styles.confirm}>
                  <span className={styles.confirmHeading}>
                    再実行される指示コメント
                  </span>
                  <div className={styles.comment}>
                    <div className={styles.commentMeta}>
                      <span className={styles.commentAuthor}>
                        {status.pending_comment_author ?? "不明"}
                      </span>
                      {status.pending_comment_created_at && (
                        <span className={styles.meta}>
                          {formatRelativeTime(
                            status.pending_comment_created_at,
                          )}
                        </span>
                      )}
                      <span className={styles.spacer} />
                      {status.pending_comment_url && (
                        <a
                          href={status.pending_comment_url}
                          target="_blank"
                          rel="noreferrer"
                          className={styles.commentLink}
                          title="GitHubで開く"
                          aria-label="コメントをGitHubで開く"
                        >
                          <Svg size={12}>
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                            <path d="M15 3h6v6M10 14 21 3" />
                          </Svg>
                        </a>
                      )}
                    </div>
                    <div className={styles.commentBody}>
                      {status.pending_message}
                    </div>
                  </div>
                  <span className={styles.confirmNote}>
                    このコメントをエージェントへの指示として再実行します。指示でない場合は再実行せず、返信で指示を出してください。
                  </span>
                  <div className={styles.btnRow}>
                    <button
                      type="button"
                      className={styles.rerunBtn}
                      onClick={rerun}
                    >
                      <Svg>
                        <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
                        <path d="M3 3v5h5" />
                      </Svg>
                      この内容で再実行
                    </button>
                    <button
                      type="button"
                      className={styles.cancelBtn}
                      onClick={() => setConfirming(false)}
                    >
                      キャンセル
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
