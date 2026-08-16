"use client";

import { useState } from "react";
import { postInstruct } from "@/lib/api";
import { formatRelativeTime } from "@/lib/time";
import type { IssueComment, IssueSummary } from "@/lib/types";
import styles from "./DecisionCard.module.css";

function latestComment(issue: IssueSummary): IssueComment | undefined {
  return issue.comments[issue.comments.length - 1];
}

function commentSummary(comment: IssueComment): string {
  // オーケストレータが投稿したコメントにはBOT_COMMENT_MARKER（HTMLコメント）が
  // 付与されている（orchestrator/orchestrator/github_client.py参照）。表示上は不要なので取り除く。
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

export default function DecisionCard({
  decision,
  onApproved,
  onReply,
  onToast,
  locked,
}: {
  decision: IssueSummary;
  onApproved: () => Promise<void>;
  onReply: (repo: string, issueNumber: number, title: string) => void;
  onToast: (text: string) => void;
  locked: boolean;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const busy = approving || locked;

  const last = latestComment(decision);
  const summary = last ? commentSummary(last) : null;
  const titleUrl =
    last?.url ??
    `https://github.com/${decision.repo}/issues/${decision.number}`;
  const repoName = decision.repo.split("/")[1];

  function openConfirm() {
    if (locked) return;
    setError(null);
    setConfirmOpen(true);
  }

  function closeConfirm() {
    if (busy) return;
    setConfirmOpen(false);
  }

  function handleConfirmApprove() {
    setApproving(true);
    setError(null);
    postInstruct(decision.repo, decision.number, "approve")
      .then(() => {
        setConfirmOpen(false);
        onToast(`${repoName} #${decision.number} を承認しました。`);
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
      aria-busy={busy}
      style={busy ? { opacity: 0.6, pointerEvents: "none" } : undefined}
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
          disabled={busy}
        >
          <CheckIcon />
          承認
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnReply}`}
          onClick={() =>
            onReply(decision.repo, decision.number, decision.title)
          }
          disabled={busy}
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
            {error && <span className={styles.confirmError}>{error}</span>}
            <div className={styles.confirmActions}>
              <button
                type="button"
                className={styles.confirmCancelBtn}
                onClick={closeConfirm}
                disabled={busy}
              >
                キャンセル
              </button>
              <button
                type="button"
                className={styles.confirmApproveBtn}
                onClick={handleConfirmApprove}
                disabled={busy}
              >
                <CheckIcon />
                {approving ? "承認中…" : "承認する"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
