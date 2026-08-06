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
  onApprove,
  onReject,
  onReply,
}: {
  decision: IssueSummary;
  onApprove: (repo: string, issueNumber: number, title: string) => void;
  onReject: (repo: string, issueNumber: number, title: string) => void;
  onReply: (repo: string, issueNumber: number, title: string) => void;
}) {
  const summary = latestCommentSummary(decision);

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

      <div className={styles.actions}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnApprove}`}
          onClick={() =>
            onApprove(decision.repo, decision.number, decision.title)
          }
        >
          ✓ 承認
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnReject}`}
          onClick={() =>
            onReject(decision.repo, decision.number, decision.title)
          }
        >
          ✕ 却下
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
    </div>
  );
}
