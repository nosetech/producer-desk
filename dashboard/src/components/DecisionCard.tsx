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

export default function DecisionCard({
  decision,
  onApproved,
  onReply,
}: {
  decision: IssueSummary;
  onApproved: () => void;
  onReply: (repo: string, issueNumber: number, title: string) => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const last = latestComment(decision);
  const summary = last ? commentSummary(last) : null;
  const titleUrl =
    last?.url ??
    `https://github.com/${decision.repo}/issues/${decision.number}`;

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
    postInstruct(decision.repo, decision.number, "approve")
      .then(() => {
        setConfirmOpen(false);
        onApproved();
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "承認に失敗しました"),
      )
      .finally(() => setApproving(false));
  }

  return (
    <div className={styles.card}>
      <div className={styles.topRow}>
        <span className={styles.repoNumber}>
          {decision.repo.split("/")[1]} #{decision.number}
        </span>
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
        {decision.title}
        <svg
          className={styles.titleIcon}
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M15 3h6v6" />
          <path d="M10 14 21 3" />
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
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
        >
          ✓ 承認
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnReply}`}
          onClick={() =>
            onReply(decision.repo, decision.number, decision.title)
          }
        >
          ↩ 返信
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
            <p
              id={`confirm-approve-${decision.repo}-${decision.number}`}
              className={styles.confirmMessage}
            >
              この提案を承認しますか？
            </p>
            <p className={styles.confirmDetail}>
              <span className={styles.confirmDetailNumber}>
                {decision.repo.split("/")[1]} #{decision.number}
              </span>{" "}
              — {decision.title}
            </p>
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
                {approving ? "承認中…" : "承認する"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
