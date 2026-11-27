"use client";

import { useState } from "react";
import { postMarkInReview } from "@/lib/api";
import type { StageDef } from "@/lib/stageProgress";
import { findIssueJob } from "@/lib/jobs";
import { cardDecisions, commentSummary, latestComment } from "@/lib/comment";
import { formatRelativeTime } from "@/lib/time";
import type { IssueComment, IssueSummary } from "@/lib/types";
import { useApp } from "./AppContext";
import DecisionPointsBox from "./DecisionPointsBox";
import JobStatus from "./JobStatus";
import LimitWaitBox from "./LimitWaitBox";
import CommentViewer from "./CommentViewer";
import DispatchDiagnosis from "./DispatchDiagnosis";
import styles from "./DecisionCard.module.css";

// orchestrator/orchestrator/instruct.py の handle_mark_in_review のon_stageと対応する。
const RELABEL_STAGES: StageDef[] = [
  {
    key: "remove",
    label: "status:needs-human-decision を外す",
    note: "DELETE /labels",
  },
  { key: "add", label: "status:in-review を付与", note: "POST /labels" },
];

function RelabelIcon({ size = 15 }: { size?: number }) {
  return (
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
    >
      <path d="M4 7h13l-3-3M20 17H7l3 3" />
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
      style={{ flex: "none" }}
    >
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="18" r="3" />
      <path d="M6 9v6M18 15V9a3 3 0 0 0-3-3h-3" />
      <path d="M12 3 9 6l3 3" />
    </svg>
  );
}

function PrCandidateIcon() {
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
      style={{ flex: "none" }}
    >
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="6" r="3" />
      <path d="M6 9v6M18 9v1a2 2 0 0 1-2 2H8" />
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
  const [relabelOpen, setRelabelOpen] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);
  const { jobs, startJob, retryJob, dismissJob } = useApp();
  // 実行中・失敗中の操作があるissueのみ操作を止める（別issue・別プロジェクトは妨げない）。
  const job = findIssueJob(jobs, decision.repo, decision.number);
  const busy = job !== undefined;

  const last = latestComment(decision);
  // 利用リミット待ち（issue #331）なら、判断事項・要約の代わりにその表示を主な情報にする。
  const limitWait = decision.limit_wait ?? null;
  // 「判断が必要な事項」があればそれを、無ければ従来の1行要約を表示する（issue #325）。
  const decisions = last && !limitWait ? cardDecisions(last.body) : null;
  const summary =
    last && !limitWait && !decisions ? commentSummary(last) : null;
  const titleUrl =
    last?.url ??
    `https://github.com/${decision.repo}/issues/${decision.number}`;
  const repoName = decision.repo.split("/")[1];
  // 判断待ちでは対応PR未作成が通常のため、候補0件のときは何も表示しない（issue #270）。
  const prCandidateCount = (decision.pr_candidates ?? []).length;
  const prUrl =
    decision.pr_number != null
      ? `https://github.com/${decision.repo}/pull/${decision.pr_number}`
      : null;

  function handleConfirmRelabel() {
    setRelabelOpen(false);
    startJob({
      kind: "relabel",
      repo: decision.repo,
      number: decision.number,
      title: decision.title,
      stages: RELABEL_STAGES,
      exec: (progressId) =>
        postMarkInReview(decision.repo, decision.number, progressId),
      successMessage: `${repoName} #${decision.number} をレビュー待ちに変更しました。`,
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
      <div className={styles.titleRow}>
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
        {prUrl ? (
          <a
            href={prUrl}
            target="_blank"
            rel="noreferrer"
            title={prUrl}
            className={styles.prLink}
          >
            <PrIcon />
            PR #{decision.pr_number}
          </a>
        ) : prCandidateCount > 1 ? (
          <span
            className={styles.prCandidateChip}
            title="対応PRの候補が複数あります。返信の前にGitHubで確認してください"
          >
            <PrCandidateIcon />
            PR候補 {prCandidateCount}件
          </span>
        ) : null}
      </div>
      {limitWait && (
        <LimitWaitBox decision={decision} limitWait={limitWait} busy={busy} />
      )}
      {decisions && (
        <DecisionPointsBox
          decisions={decisions}
          onViewFull={() => setViewerOpen(true)}
        />
      )}
      {summary && (
        <div className={styles.summary}>
          <span className={styles.aiTag}>AI</span>
          <div className={styles.summaryBody}>
            <span className={styles.summaryText}>{summary}</span>
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

      <div className={styles.actions}>
        <div className={`${styles.mainActs} ${busy ? styles.actionsBusy : ""}`}>
          <button
            type="button"
            className={styles.replyBtn}
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
        {last && (
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
        )}
      </div>

      <button
        type="button"
        className={styles.relabelBtn}
        onClick={() => !busy && setRelabelOpen(true)}
        disabled={busy}
        title="AIの遷移漏れを修正：ラベルを status:in-review に付け替えます"
      >
        <RelabelIcon />
        レビュー待ちに変更
      </button>

      <DispatchDiagnosis
        repo={decision.repo}
        number={decision.number}
        title={decision.title}
        busy={busy}
      />

      {viewerOpen && last && (
        <CommentViewer
          comments={decision.comments}
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

      {relabelOpen && (
        <div
          className={styles.confirmOverlay}
          onClick={() => setRelabelOpen(false)}
        >
          <div
            className={styles.confirmDialog}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={`confirm-relabel-${decision.repo}-${decision.number}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.confirmHeadingRow}>
              <span
                className={`${styles.confirmIconBadge} ${styles.relabelBadge}`}
              >
                <RelabelIcon size={18} />
              </span>
              <span
                id={`confirm-relabel-${decision.repo}-${decision.number}`}
                className={styles.confirmMessage}
              >
                レビュー待ちに変更しますか？
              </span>
            </div>
            <p className={styles.confirmDetail}>
              <span className={styles.confirmDetailNumber}>
                {repoName} #{decision.number}
              </span>{" "}
              — {decision.title}
            </p>
            <p className={styles.relabelNote}>
              このissueをレビュー待ちに変更します。AIへの指示コメントは投稿されず、ラベルのみ変更されます。
            </p>
            <div className={styles.labelDiff}>
              <span className={styles.labelFrom}>
                status:needs-human-decision
              </span>
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="var(--text-tertiary)"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ flex: "none" }}
              >
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
              <span className={styles.labelTo}>status:in-review</span>
            </div>
            <div className={styles.confirmActions}>
              <button
                type="button"
                className={styles.confirmCancelBtn}
                onClick={() => setRelabelOpen(false)}
              >
                キャンセル
              </button>
              <button
                type="button"
                className={styles.relabelConfirmBtn}
                onClick={handleConfirmRelabel}
              >
                変更する
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
