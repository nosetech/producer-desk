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
  const last = latestComment(decision);
  const summary = last ? commentSummary(last) : null;
  const titleUrl =
    last?.url ??
    `https://github.com/${decision.repo}/issues/${decision.number}`;

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
