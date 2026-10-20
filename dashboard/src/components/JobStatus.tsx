"use client";

import {
  failureMessage,
  progressCount,
  stageIndex,
  type Job,
} from "@/lib/jobs";
import { resolveStages } from "@/lib/stageProgress";
import { SpinnerIcon, StageList } from "./StageProgress";
import styles from "./JobStatus.module.css";

const HEADING: Record<Job["kind"], { running: string; failed: string }> = {
  approve: { running: "承認を処理中", failed: "承認に失敗しました" },
  merge: { running: "マージを処理中", failed: "マージに失敗しました" },
  reply: { running: "返信を送信中", failed: "返信の送信に失敗しました" },
  new: { running: "作成を処理中", failed: "作成に失敗しました" },
  rerun: { running: "再実行を処理中", failed: "再実行に失敗しました" },
};

export function ErrorIcon({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--warn)"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={styles.icon}
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v4M12 16h.01" />
    </svg>
  );
}

export function RetryDismiss({
  onRetry,
  onDismiss,
}: {
  onRetry: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className={styles.errorActions}>
      <button type="button" className={styles.retryBtn} onClick={onRetry}>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.3"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
          <path d="M3 3v5h5" />
        </svg>
        再試行
      </button>
      <button type="button" className={styles.dismissBtn} onClick={onDismiss}>
        閉じる
      </button>
    </div>
  );
}

/** カード内に出す、そのissueの操作の段階進捗・失敗表示（issue #212）。 */
export default function JobStatus({
  job,
  onRetry,
  onDismiss,
}: {
  job: Job;
  onRetry: () => void;
  onDismiss: () => void;
}) {
  const err = job.status === "error";
  const stages = resolveStages(
    job.stages,
    job.polledStage,
    err ? "error" : "busy",
  );
  return (
    <div
      role="status"
      aria-live="polite"
      className={`${styles.box} ${err ? styles.boxError : ""}`}
    >
      <div className={styles.head}>
        {err ? <ErrorIcon /> : <SpinnerIcon />}
        <span className={`${styles.heading} ${err ? styles.headingError : ""}`}>
          {err ? HEADING[job.kind].failed : HEADING[job.kind].running}
        </span>
        <span className={styles.spacer} />
        <span className={styles.count}>
          {progressCount(job, stageIndex(job))}
        </span>
      </div>
      <StageList stages={stages} bare />
      {err && (
        <div className={styles.errorBlock}>
          <span className={styles.errorText}>
            {failureMessage(job)}
            {job.errorMessage ? ` ${job.errorMessage}` : ""}
            通信状況を確認して再試行してください。
          </span>
          <RetryDismiss onRetry={onRetry} onDismiss={onDismiss} />
        </div>
      )}
    </div>
  );
}
