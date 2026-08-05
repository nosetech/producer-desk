"use client";

import { useRef, useState } from "react";
import { postInstruct } from "@/lib/api";
import { formatRelativeTime } from "@/lib/time";
import type { IssueSummary } from "@/lib/types";
import styles from "./DecisionCard.module.css";

function latestCommentSummary(issue: IssueSummary): string | null {
  const last = issue.comments[issue.comments.length - 1];
  if (!last) return null;
  // オーケストレータが投稿したコメントにはBOT_COMMENT_MARKER（HTMLコメント）が
  // 付与されている（orchestrator/orchestrator/github_client.py参照）。表示上は不要なので取り除く。
  const withoutMarkers = last.body.replace(/<!--[\s\S]*?-->/g, "");
  const oneLine = withoutMarkers.replace(/\s+/g, " ").trim();
  return oneLine.length > 140 ? `${oneLine.slice(0, 140)}…` : oneLine;
}

export default function DecisionCard({
  decision,
  onReply,
  onActed,
}: {
  decision: IssueSummary;
  onReply: (repo: string, issueNumber: number, title: string) => void;
  onActed: () => void;
}) {
  const [confirmingApprove, setConfirmingApprove] = useState(false);
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [submitting, setSubmitting] = useState<"approve" | "reject" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const confirmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleApproveClick() {
    if (!confirmingApprove) {
      setConfirmingApprove(true);
      confirmTimer.current = setTimeout(
        () => setConfirmingApprove(false),
        4000,
      );
      return;
    }
    if (confirmTimer.current) clearTimeout(confirmTimer.current);
    setConfirmingApprove(false);
    setSubmitting("approve");
    setError(null);
    postInstruct(decision.repo, decision.number, "approve")
      .then(() => onActed())
      .catch((e) =>
        setError(e instanceof Error ? e.message : "承認に失敗しました"),
      )
      .finally(() => setSubmitting(null));
  }

  function handleRejectSubmit() {
    setSubmitting("reject");
    setError(null);
    postInstruct(
      decision.repo,
      decision.number,
      "reject",
      rejectReason.trim() || undefined,
    )
      .then(() => {
        setShowRejectForm(false);
        setRejectReason("");
        onActed();
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "却下に失敗しました"),
      )
      .finally(() => setSubmitting(null));
  }

  const summary = latestCommentSummary(decision);
  const busy = submitting !== null;

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
      <div className={styles.title}>{decision.title}</div>
      {summary && (
        <div className={styles.summary}>
          <span className={styles.aiTag}>AI</span>
          <span>{summary}</span>
        </div>
      )}

      {showRejectForm ? (
        <div className={styles.rejectForm}>
          <textarea
            className={styles.rejectTextarea}
            placeholder="却下理由（任意）"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            disabled={busy}
          />
          <div className={styles.rejectFormActions}>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnReject}`}
              onClick={handleRejectSubmit}
              disabled={busy}
            >
              却下する
            </button>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnReply}`}
              onClick={() => {
                setShowRejectForm(false);
                setRejectReason("");
              }}
              disabled={busy}
            >
              キャンセル
            </button>
          </div>
        </div>
      ) : (
        <div className={styles.actions}>
          <button
            type="button"
            className={`${styles.btn} ${styles.btnApprove}`}
            onClick={handleApproveClick}
            disabled={busy}
          >
            {confirmingApprove ? "本当に承認しますか？" : "✓ 承認"}
          </button>
          <button
            type="button"
            className={`${styles.btn} ${styles.btnReject}`}
            onClick={() => setShowRejectForm(true)}
            disabled={busy}
          >
            ✕ 却下
          </button>
          <button
            type="button"
            className={`${styles.btn} ${styles.btnReply}`}
            onClick={() =>
              onReply(decision.repo, decision.number, decision.title)
            }
            disabled={busy}
          >
            ↩ 返信
          </button>
        </div>
      )}
      {error && <span className={styles.error}>{error}</span>}
    </div>
  );
}
