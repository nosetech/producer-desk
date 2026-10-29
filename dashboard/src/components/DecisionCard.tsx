"use client";

import { useState } from "react";
import { postInstruct } from "@/lib/api";
import type { StageDef } from "@/lib/stageProgress";
import { findIssueJob } from "@/lib/jobs";
import { commentSummary, latestComment } from "@/lib/comment";
import { formatRelativeTime } from "@/lib/time";
import type { IssueComment, IssueSummary } from "@/lib/types";
import { useApp } from "./AppContext";
import JobStatus from "./JobStatus";
import CommentViewer from "./CommentViewer";
import DispatchDiagnosis from "./DispatchDiagnosis";
import styles from "./DecisionCard.module.css";

// orchestrator/orchestrator/instruct.py の apply_instruction（コメント投稿は
// handle_instructで、以降はapply_instruction内でon_stageコールバックが通知する）
// と対応する。
const APPROVE_STAGES: StageDef[] = [
  { key: "comment", label: "コメントを投稿", note: "POST comment" },
  { key: "label", label: "ラベルを更新", note: "label" },
  { key: "dispatch", label: "エージェントへ引き渡し", note: "queue" },
];

function CheckIcon({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function ReplyIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M9 17 4 12l5-5" />
      <path d="M4 12h11a5 5 0 0 1 0 10" />
    </svg>
  );
}

export default function DecisionCard({
  decision,
  onReply,
}: {
  decision: IssueSummary;
  onReply: (
    repo: string,
    issueNumber: number,
    title: string,
    comments?: IssueComment[],
  ) => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);
  const { jobs, startJob, retryJob, dismissJob } = useApp();
  // 実行中・失敗中の操作があるissueのみ操作を止める（別issue・別プロジェクトは妨げない）。
  const job = findIssueJob(jobs, decision.repo, decision.number);
  const busy = job !== undefined;

  const last = latestComment(decision);
  const summary = last ? commentSummary(last) : null;
  const titleUrl =
    last?.url ??
    `https://github.com/${decision.repo}/issues/${decision.number}`;
  const repoName = decision.repo.split("/")[1];

  function openConfirm() {
    if (busy) return;
    setConfirmOpen(true);
  }

  // 承認はバックグラウンドのジョブとして実行し、確認ダイアログは即座に閉じる。
  // 進捗・失敗はカード内に表示する（issue #212）。
  function handleConfirmApprove() {
    setConfirmOpen(false);
    startJob({
      kind: "approve",
      repo: decision.repo,
      number: decision.number,
      title: decision.title,
      stages: APPROVE_STAGES,
      exec: (progressId) =>
        postInstruct(
          decision.repo,
          decision.number,
          "approve",
          undefined,
          progressId,
        ),
      successMessage: `${repoName} #${decision.number} を承認しました。`,
    });
  }

  return (
    <div
      className={`${styles.card} ${
        job?.status === "error"
          ? styles.cardJobError
          : job
            ? styles.cardJobRunning
            : ""
      }`}
      aria-busy={job?.status === "running"}
    >
      <div className={styles.topRow}>
        <div className={styles.repoGroup}>
          <span className={styles.repoName}>{repoName}</span>
          <span className={styles.repoNum}>#{decision.number}</span>
        </div>
        <span className={styles.time}>
          {formatRelativeTime(decision.updated_at)}
        </span>
      </div>
      <a
        href={titleUrl}
        target="_blank"
        rel="noreferrer"
        className={styles.title}
      >
        <span>{decision.title}</span>
        <svg
          className={styles.titleIcon}
          width="13"
          height="13"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
          <path d="M15 3h6v6M10 14 21 3" />
        </svg>
      </a>
      {summary && (
        <div className={styles.summary}>
          <span className={styles.aiTag}>AI</span>
          <div className={styles.summaryBody}>
            <span className={styles.summaryText}>{summary}</span>
            <button
              type="button"
              className={styles.fullTextBtn}
              onClick={() => setViewerOpen(true)}
              aria-haspopup="dialog"
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.3"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              </svg>
              全文を表示
            </button>
          </div>
        </div>
      )}

      {job && (
        <JobStatus
          job={job}
          onRetry={() => retryJob(job.key)}
          onDismiss={() => dismissJob(job.key)}
        />
      )}

      <div className={`${styles.actions} ${busy ? styles.actionsBusy : ""}`}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnApprove}`}
          onClick={openConfirm}
          disabled={busy}
        >
          <CheckIcon />
          承認
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnReply}`}
          onClick={() =>
            onReply(
              decision.repo,
              decision.number,
              decision.title,
              decision.comments,
            )
          }
          disabled={busy}
        >
          <ReplyIcon />
          返信
        </button>
      </div>

      <DispatchDiagnosis
        repo={decision.repo}
        number={decision.number}
        title={decision.title}
        busy={busy}
      />

      {viewerOpen && last && (
        <CommentViewer
          comment={last}
          label={`${repoName} #${decision.number}`}
          kindLabel="判断待ち"
          title={decision.title}
          onClose={() => setViewerOpen(false)}
          onReply={() => {
            setViewerOpen(false);
            onReply(
              decision.repo,
              decision.number,
              decision.title,
              decision.comments,
            );
          }}
          replyDisabled={busy}
        />
      )}

      {confirmOpen && (
        <div
          className={styles.confirmOverlay}
          onClick={() => setConfirmOpen(false)}
        >
          <div
            className={styles.confirmDialog}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={`confirm-approve-${decision.repo}-${decision.number}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.confirmHeadingRow}>
              <span className={styles.confirmIconBadge}>
                <CheckIcon size={18} />
              </span>
              <span
                id={`confirm-approve-${decision.repo}-${decision.number}`}
                className={styles.confirmMessage}
              >
                この提案を承認しますか？
              </span>
            </div>
            <p className={styles.confirmDetail}>
              <span className={styles.confirmDetailNumber}>
                {repoName} #{decision.number}
              </span>{" "}
              — {decision.title}
            </p>
            <div className={styles.confirmActions}>
              <button
                type="button"
                className={styles.confirmCancelBtn}
                onClick={() => setConfirmOpen(false)}
              >
                キャンセル
              </button>
              <button
                type="button"
                className={styles.confirmApproveBtn}
                onClick={handleConfirmApprove}
              >
                <CheckIcon />
                承認する
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
