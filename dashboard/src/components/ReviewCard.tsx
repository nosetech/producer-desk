"use client";

import { useState } from "react";
import { postInstruct } from "@/lib/api";
import { formatRelativeTime } from "@/lib/time";
import type { IssueComment, IssueSummary } from "@/lib/types";
import styles from "./ReviewCard.module.css";

function latestComment(issue: IssueSummary): IssueComment | undefined {
  return issue.comments[issue.comments.length - 1];
}

function commentSummary(comment: IssueComment): string {
  const withoutMarkers = comment.body.replace(/<!--[\s\S]*?-->/g, "");
  return withoutMarkers.replace(/\s+/g, " ").trim();
}

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

function PrIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="18" r="3" />
      <path d="M6 9v6M18 15V9a3 3 0 0 0-3-3h-3" />
      <path d="M12 3 9 6l3 3" />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={styles.warningIcon}
    >
      <path d="M12 9v4M12 17h.01" />
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h16.9a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    </svg>
  );
}

export default function ReviewCard({
  review,
  onApproved,
  onReply,
  onToast,
}: {
  review: IssueSummary;
  onApproved: () => Promise<void>;
  onReply: (repo: string, issueNumber: number, title: string) => void;
  onToast: (text: string) => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const last = latestComment(review);
  const summary = last ? commentSummary(last) : null;
  const titleUrl =
    last?.url ?? `https://github.com/${review.repo}/issues/${review.number}`;
  const prUrl =
    review.pr_number != null
      ? `https://github.com/${review.repo}/pull/${review.pr_number}`
      : null;
  const repoName = review.repo.split("/")[1];

  function openConfirm() {
    setError(null);
    setConfirmOpen(true);
  }

  function closeConfirm() {
    if (approving) return;
    setConfirmOpen(false);
  }

  function handleConfirmApprove() {
    setApproving(true);
    setError(null);
    postInstruct(review.repo, review.number, "approve")
      .then(() => {
        setConfirmOpen(false);
        onToast(`${repoName} #${review.number} をマージ & クローズしました。`);
        return onApproved();
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "承認に失敗しました"),
      )
      .finally(() => setApproving(false));
  }

  return (
    <div
      className={styles.card}
      aria-busy={approving}
      style={approving ? { opacity: 0.6, pointerEvents: "none" } : undefined}
    >
      <div className={styles.topRow}>
        <div className={styles.repoGroup}>
          <span className={styles.repoName}>{repoName}</span>
          <span className={styles.repoNum}>#{review.number}</span>
        </div>
        <span className={styles.time}>
          {formatRelativeTime(review.updated_at)}
        </span>
      </div>
      <div className={styles.titleRow}>
        <a
          href={titleUrl}
          target="_blank"
          rel="noreferrer"
          className={styles.title}
        >
          <span>{review.title}</span>
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
        {prUrl && (
          <a
            href={prUrl}
            target="_blank"
            rel="noreferrer"
            className={styles.prLink}
          >
            <PrIcon />
            PR #{review.pr_number}
          </a>
        )}
      </div>
      {summary && (
        <div className={styles.summary}>
          <span className={styles.aiTag}>AI</span>
          <span className={styles.summaryText} title={summary}>
            {summary}
          </span>
        </div>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnApprove}`}
          onClick={openConfirm}
          disabled={approving}
        >
          <CheckIcon />
          承認
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnReply}`}
          onClick={() => onReply(review.repo, review.number, review.title)}
          disabled={approving}
        >
          <ReplyIcon />
          返信
        </button>
      </div>

      {confirmOpen && (
        <div className={styles.confirmOverlay} onClick={closeConfirm}>
          <div
            className={styles.confirmDialog}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={`confirm-review-${review.repo}-${review.number}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.confirmHeadingRow}>
              <span className={styles.confirmIconBadge}>
                <CheckIcon size={18} />
              </span>
              <span
                id={`confirm-review-${review.repo}-${review.number}`}
                className={styles.confirmMessage}
              >
                このレビューを承認しますか？
              </span>
            </div>
            <p className={styles.confirmDetail}>
              <span className={styles.confirmDetailNumber}>
                {repoName} #{review.number}
              </span>{" "}
              — {review.title}
            </p>
            <div className={styles.warningBanner}>
              <WarningIcon />
              <div className={styles.warningText}>
                承認すると、
                <strong>対象PRのマージと該当issueのクローズ</strong>
                まで自動で実行されます。この操作は元に戻せません。
              </div>
            </div>
            {error && <span className={styles.confirmError}>{error}</span>}
            <div className={styles.confirmActions}>
              <button
                type="button"
                className={styles.confirmCancelBtn}
                onClick={closeConfirm}
                disabled={approving}
              >
                キャンセル
              </button>
              <button
                type="button"
                className={styles.confirmApproveBtn}
                onClick={handleConfirmApprove}
                disabled={approving}
              >
                <CheckIcon />
                {approving ? "マージ中…" : "マージして承認"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
