"use client";

import { useState } from "react";
import { jobLabel, progressCount, stageIndex, type Job } from "@/lib/jobs";
import { useApp } from "./AppContext";
import { ErrorIcon, RetryDismiss } from "./JobStatus";
import { SpinnerIcon } from "./StageProgress";
import styles from "./BackgroundJobs.module.css";

/**
 * 対応するカードを持たない操作（新規作成・カード外のissueへの返信）の処理状況を
 * ヘッダーにまとめて表示する（issue #212）。
 */
export default function BackgroundJobs() {
  const { state, jobs, retryJob, dismissJob } = useApp();
  const [open, setOpen] = useState(false);

  const cardKeys = new Set(
    [...state.decisions, ...state.reviews].map((i) => `${i.repo}#${i.number}`),
  );
  const list: Job[] = jobs.filter(
    (j) => j.kind === "new" || !cardKeys.has(j.key),
  );
  if (list.length === 0) return null;

  const running = list.filter((j) => j.status === "running").length;
  const failed = list.length - running;
  const label = running > 0 ? `${running}件 処理中` : `${failed}件 失敗`;
  const summary = [
    running ? `${running}件 処理中` : "",
    failed ? `${failed}件 失敗` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const aria = `操作の処理状況: ${summary}`;

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className={`${styles.pill} ${running === 0 ? styles.pillFailed : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={aria}
        title={aria}
      >
        {running > 0 && <SpinnerIcon />}
        {running === 0 && <ErrorIcon size={14} />}
        <span>{label}</span>
        {failed > 0 && running > 0 && (
          <span className={styles.failBadge}>{failed}件 失敗</span>
        )}
      </button>
      {open && (
        <>
          <div className={styles.scrim} onClick={() => setOpen(false)} />
          <div role="dialog" aria-label="操作の処理状況" className={styles.pop}>
            <div className={styles.popHead}>
              <span className={styles.popTitle}>新規作成・返信の処理</span>
              <span className={styles.popSummary}>{summary}</span>
            </div>
            {list.map((j) => {
              const err = j.status === "error";
              const idx = stageIndex(j);
              const total = j.stages.length;
              const current = j.stages[Math.min(idx + 1, total - 1)];
              return (
                <div
                  key={j.key}
                  className={`${styles.row} ${err ? styles.rowError : ""}`}
                >
                  <div className={styles.rowTop}>
                    {err ? <ErrorIcon size={14} /> : <SpinnerIcon />}
                    <span className={styles.rowLabel}>{jobLabel(j)}</span>
                    <span className={styles.spacer} />
                    <span className={styles.count}>
                      {progressCount(j, idx)}
                    </span>
                  </div>
                  <span className={styles.rowTitle}>{j.title}</span>
                  <div className={styles.bar}>
                    <div
                      className={`${styles.barFill} ${err ? styles.barError : ""}`}
                      style={{
                        width: `${Math.round(((idx + 1 + (err ? 0 : 0.5)) / total) * 100)}%`,
                      }}
                    />
                  </div>
                  <span
                    className={`${styles.stageText} ${err ? styles.stageTextError : ""}`}
                  >
                    {err
                      ? `${current.label}に失敗しました。${j.errorMessage ?? ""}`
                      : `${current.label}…`}
                  </span>
                  {err && (
                    <RetryDismiss
                      onRetry={() => retryJob(j.key)}
                      onDismiss={() => dismissJob(j.key)}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
