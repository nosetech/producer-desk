"use client";

import { useState } from "react";
import { PrSelectionRequiredError, postInstruct } from "@/lib/api";
import type { StageDef } from "@/lib/stageProgress";
import { findIssueJob } from "@/lib/jobs";
import { commentSummary, latestComment } from "@/lib/comment";
import { formatRelativeTime } from "@/lib/time";
import type { IssueComment, IssueSummary, PrCandidate } from "@/lib/types";
import { useApp } from "./AppContext";
import JobStatus from "./JobStatus";
import CommentViewer from "./CommentViewer";
import DispatchDiagnosis from "./DispatchDiagnosis";
import styles from "./ReviewCard.module.css";

// orchestrator/orchestrator/instruct.py の handle_instruct（STATUS_IN_REVIEW分岐）の
// on_stageコールバックと対応する。ブランチ削除・worktree同期は失敗しても処理全体は
// 成功扱いになるため、on_stageは成功時と区別できるよう `${key}_skipped` を返すことがある
// （StageProgress.resolveStagesが解釈する）。
const MERGE_STAGES: StageDef[] = [
  { key: "merge", label: "PRをマージ", note: "merge" },
  { key: "close", label: "issueをクローズ", note: "close" },
  { key: "label", label: "ラベルを更新", note: "label" },
  { key: "branch_delete", label: "ブランチを削除", note: "branch" },
  { key: "worktree_sync", label: "worktreeを同期", note: "worktree" },
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

function PrNoneIcon() {
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
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v4M12 16h.01" />
    </svg>
  );
}

function ExternalLinkIcon({ size = 13 }: { size?: number }) {
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
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <path d="M15 3h6v6M10 14 21 3" />
    </svg>
  );
}

function PrEmptyIcon() {
  return (
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.1"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M6 9v6" />
      <path d="m15 15 6 6M21 15l-6 6" />
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
  onReply,
}: {
  review: IssueSummary;
  onReply: (
    repo: string,
    issueNumber: number,
    title: string,
    comment?: IssueComment,
  ) => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);
  // 承認時に409（pr_selection_required）で返された最新の候補。ポーリング後に候補が
  // 変わった場合に、カードの`review.pr_candidates`より優先して選択UIに使う（issue #206）。
  const [candidatesOverride, setCandidatesOverride] = useState<
    PrCandidate[] | null
  >(null);
  const [pickedPr, setPickedPr] = useState<number | null>(null);
  const { jobs, startJob, retryJob, dismissJob } = useApp();
  // 実行中・失敗中の操作があるissueのみ操作を止める（別issue・別プロジェクトは妨げない）。
  const job = findIssueJob(jobs, review.repo, review.number);
  const busy = job !== undefined;

  const last = latestComment(review);
  const summary = last ? commentSummary(last) : null;
  const titleUrl =
    last?.url ?? `https://github.com/${review.repo}/issues/${review.number}`;
  const prUrl =
    review.pr_number != null
      ? `https://github.com/${review.repo}/pull/${review.pr_number}`
      : null;
  const repoName = review.repo.split("/")[1];

  // 対応PRが一意に特定できている（候補ちょうど1件）場合のみ従来の確認ダイアログ。
  // 複数・0件の場合はマージするPRを選ぶダイアログを開く（issue #206）。
  const candidates = candidatesOverride ?? review.pr_candidates ?? [];
  const isSinglePr = candidatesOverride
    ? candidatesOverride.length === 1
    : review.pr_number != null;
  const isPicker = !isSinglePr;
  const isEmpty = isPicker && candidates.length === 0;
  const pickedCandidate = candidates.find((c) => c.number === pickedPr) ?? null;
  const approveBlocked = isPicker && pickedCandidate === null;
  const prCountLabel = `PR候補 ${candidates.length}件`;
  const mergeTargetText = pickedCandidate
    ? `PR #${pickedCandidate.number} のマージと該当issueのクローズ`
    : isPicker
      ? "選択したPRのマージと該当issueのクローズ"
      : "対象PRのマージと該当issueのクローズ";
  const confirmHeading = isSinglePr
    ? "このレビューを承認しますか？"
    : isEmpty
      ? "対応PRを特定できません"
      : "マージするPRを選択";

  function openConfirm() {
    if (busy) return;
    setPickedPr(null);
    setConfirmOpen(true);
  }

  function closeConfirm() {
    setConfirmOpen(false);
    setCandidatesOverride(null);
    setPickedPr(null);
  }

  // マージはバックグラウンドのジョブとして実行し、確認ダイアログは即座に閉じる。
  // 進捗・失敗はカード内に表示する（issue #212）。
  function handleConfirmApprove() {
    if (approveBlocked) return;
    const prNumber = isPicker ? (pickedPr ?? undefined) : undefined;
    setConfirmOpen(false);
    startJob({
      kind: "merge",
      repo: review.repo,
      number: review.number,
      title: review.title,
      stages: MERGE_STAGES,
      exec: (progressId) =>
        postInstruct(
          review.repo,
          review.number,
          "approve",
          undefined,
          progressId,
          prNumber,
        ),
      successMessage: `${repoName} #${review.number} をマージ & クローズしました。`,
      onFailure: (e) => {
        if (!(e instanceof PrSelectionRequiredError)) return false;
        // 候補が変わっていた（または特定できなかった）場合。自動マージはされて
        // いないため、返された最新の候補で選び直させる。
        setCandidatesOverride(e.candidates);
        setPickedPr(null);
        setConfirmOpen(true);
        return true;
      },
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
        {prUrl ? (
          <a
            href={prUrl}
            target="_blank"
            rel="noreferrer"
            className={styles.prLink}
          >
            <PrIcon />
            PR #{review.pr_number}
          </a>
        ) : (review.pr_candidates ?? []).length > 1 ? (
          <span
            className={styles.prCandidateChip}
            title="対応PRの候補が複数あります。承認時にマージするPRを選択します"
          >
            <PrCandidateIcon />
            PR候補 {(review.pr_candidates ?? []).length}件
          </span>
        ) : (
          <span
            className={styles.prNoneChip}
            title="このissueに対応するPRを特定できませんでした"
          >
            <PrNoneIcon />
            PR未特定
          </span>
        )}
      </div>
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
            onReply(review.repo, review.number, review.title, last)
          }
          disabled={busy}
        >
          <ReplyIcon />
          返信
        </button>
      </div>

      <DispatchDiagnosis
        repo={review.repo}
        number={review.number}
        title={review.title}
        busy={busy}
      />

      {viewerOpen && last && (
        <CommentViewer
          comment={last}
          label={`${repoName} #${review.number}`}
          kindLabel="レビュー待ち"
          title={review.title}
          onClose={() => setViewerOpen(false)}
          onReply={() => {
            setViewerOpen(false);
            onReply(review.repo, review.number, review.title, last);
          }}
          replyDisabled={busy}
        />
      )}

      {confirmOpen && (
        <div className={styles.confirmOverlay} onClick={closeConfirm}>
          <div
            className={`${styles.confirmDialog} ${isSinglePr ? "" : styles.confirmDialogWide}`}
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
                {confirmHeading}
              </span>
            </div>
            <p className={styles.confirmDetail}>
              <span className={styles.confirmDetailNumber}>
                {repoName} #{review.number}
              </span>{" "}
              — {review.title}
            </p>
            {isPicker && candidates.length > 0 && (
              <div className={styles.prPicker}>
                <div className={styles.prPickerHeader}>
                  <span className={styles.prPickerCount}>{prCountLabel}</span>
                  <span className={styles.prPickerHint}>
                    {pickedCandidate
                      ? `#${pickedCandidate.number} をマージします`
                      : "1件選択してください"}
                  </span>
                </div>
                <div
                  className={styles.prRadioGroup}
                  role="radiogroup"
                  aria-label="マージするPR"
                >
                  {candidates.map((c) => {
                    const selected = c.number === pickedPr;
                    const pick = () => {
                      setPickedPr(c.number);
                    };
                    return (
                      <div
                        key={c.number}
                        role="radio"
                        tabIndex={0}
                        aria-checked={selected}
                        className={`${styles.prRow} ${selected ? styles.prRowSelected : ""}`}
                        onClick={pick}
                        onKeyDown={(e) => {
                          if (
                            (e.key === "Enter" || e.key === " ") &&
                            e.target === e.currentTarget
                          ) {
                            e.preventDefault();
                            pick();
                          }
                        }}
                      >
                        <span className={styles.prRadioRing}>
                          <span className={styles.prRadioDot} />
                        </span>
                        <div className={styles.prRowBody}>
                          <div className={styles.prRowTitleLine}>
                            <span className={styles.prRowTitle}>{c.title}</span>
                            {c.is_draft && (
                              <span className={styles.prDraftBadge}>DRAFT</span>
                            )}
                          </div>
                          <div className={styles.prRowMeta}>
                            <span className={styles.prRowNumber}>
                              #{c.number}
                            </span>
                            <span className={styles.prRowBranches}>
                              {c.head_ref_name}{" "}
                              <span className={styles.prRowBranchArrow}>→</span>{" "}
                              {c.base_ref_name}
                            </span>
                          </div>
                        </div>
                        <a
                          href={c.url}
                          target="_blank"
                          rel="noreferrer"
                          className={styles.prRowLink}
                          title="GitHubで開く"
                          aria-label={`PR #${c.number} をGitHubで開く`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ExternalLinkIcon />
                        </a>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {isPicker && pickedCandidate?.is_draft && (
              <div
                className={`${styles.warningBanner} ${styles.confirmDraftWarning}`}
                role="alert"
              >
                <WarningIcon />
                <div className={styles.warningText}>
                  <strong>このPRはDraftです。</strong>
                  Draft
                  PRはマージできないため、承認が失敗する可能性があります。Ready
                  for reviewにしてから承認することを推奨します。
                </div>
              </div>
            )}
            {isEmpty && (
              <div className={styles.prEmpty}>
                <span className={styles.prEmptyIcon}>
                  <PrEmptyIcon />
                </span>
                <div className={styles.prEmptyTitle}>
                  対応PRが見つかりません
                </div>
                <p className={styles.prEmptyText}>
                  GitHub上でPRを確認してください。
                </p>
                <a
                  href={`https://github.com/${review.repo}/pulls`}
                  target="_blank"
                  rel="noreferrer"
                  className={styles.prLink}
                >
                  <ExternalLinkIcon size={12} />
                  GitHubでPR一覧を開く
                </a>
              </div>
            )}
            {!isEmpty && (
              <div className={styles.warningBanner}>
                <WarningIcon />
                <div className={styles.warningText}>
                  承認すると、
                  <strong>{mergeTargetText}</strong>
                  まで自動で実行されます。この操作は元に戻せません。
                </div>
              </div>
            )}
            <div className={styles.confirmActions}>
              <button
                type="button"
                className={styles.confirmCancelBtn}
                onClick={closeConfirm}
              >
                キャンセル
              </button>
              <button
                type="button"
                className={`${styles.confirmApproveBtn} ${approveBlocked ? styles.confirmApproveBtnBlocked : ""}`}
                onClick={handleConfirmApprove}
                disabled={approveBlocked}
              >
                <CheckIcon />
                マージして承認
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
