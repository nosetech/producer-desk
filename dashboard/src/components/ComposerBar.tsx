"use client";

import { useEffect, useRef, useState } from "react";
import { fetchProgress, postCreateIssue, postInstruct } from "@/lib/api";
import { shortRepoName } from "@/lib/projectStatus";
import type { Dispatch, InstructAction } from "@/lib/types";
import styles from "./ComposerBar.module.css";

export interface IssueRef {
  repo: string;
  number: number;
  title: string;
}

export type ComposerMode = "reply" | "new";

interface Stage {
  // orchestrator/orchestrator/instruct.py の on_stage コールバックが通知する
  // 実際の完了ステップ名（server.py の ProgressStore 経由で /api/progress
  // からポーリングで取得する）と対応させるキー。
  key: string;
  label: string;
  note: string;
}

// 実際の処理順（orchestrator/orchestrator/instruct.py の handle_instruct /
// handle_create_issue）に合わせた段階。表示中の段階は擬似進行ではなく、
// サーバがon_stageコールバックで実際に完了したタイミングをポーリングで反映する。
const REPLY_STAGES: Stage[] = [
  { key: "comment", label: "コメントを投稿", note: "POST comment" },
  { key: "label", label: "ラベルを更新", note: "label" },
  { key: "dispatch", label: "エージェントへ引き渡し", note: "queue" },
];
const CREATE_IMMEDIATE_STAGES: Stage[] = [
  { key: "issue", label: "issueを作成", note: "POST /issues" },
  { key: "label", label: "ラベルを付与", note: "label" },
  { key: "dispatch", label: "エージェントへ引き渡し", note: "queue" },
];
const CREATE_QUEUED_STAGES: Stage[] = [
  { key: "issue", label: "issueを作成", note: "POST /issues" },
  { key: "label", label: "todoとして登録", note: "label" },
];

const PROGRESS_POLL_INTERVAL_MS = 250;

// `crypto.randomUUID()`はセキュアコンテキスト（HTTPS/localhost）でのみ使える。
// このダッシュボードは同一LAN内へのプレーンHTTPでの配布を前提としており
// （CLAUDE.md「確定済みの設計判断」）、LAN内の別端末からアクセスした場合は
// セキュアコンテキストにならないため使用しない。
function randomProgressId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function SpinnerIcon() {
  return (
    <svg
      className={styles.spinnerSvg}
      width="15"
      height="15"
      viewBox="0 0 42 42"
    >
      <circle
        className={styles.spinnerTrack}
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
      />
      <circle
        className={styles.spinnerArc}
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray="34 200"
      />
    </svg>
  );
}

function StageList({
  stages,
  stageIndex,
}: {
  stages: Stage[];
  stageIndex: number;
}) {
  return (
    <div className={styles.stagePanel}>
      {stages.map((s, i) => {
        const state =
          i < stageIndex ? "done" : i === stageIndex ? "active" : "pending";
        return (
          <div className={styles.stageRow} key={s.key}>
            {state === "done" ? (
              <svg
                className={styles.stageDot}
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="var(--accent-green)"
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M20 6 9 17l-5-5" />
              </svg>
            ) : (
              <span className={styles.stageDot}>
                <span
                  className={
                    state === "active"
                      ? styles.stageDotActive
                      : styles.stageDotPending
                  }
                />
              </span>
            )}
            <span
              className={`${styles.stageLabel} ${
                state === "active"
                  ? styles.stageLabelActive
                  : state === "pending"
                    ? styles.stageLabelPending
                    : styles.stageLabelDone
              }`}
            >
              {s.label}
            </span>
            <span className={styles.stageLine} />
            <span className={styles.stageNote}>{s.note}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function ComposerBar({
  open,
  mode,
  replyTarget,
  onClearReplyTarget,
  onOpen,
  onClose,
  repos,
  newTaskRepo,
  onNewTaskRepoChange,
  onSubmitted,
  onReplySubmittingChange,
}: {
  open: boolean;
  mode: ComposerMode;
  replyTarget: IssueRef | null;
  onClearReplyTarget: () => void;
  onOpen: () => void;
  onClose: () => void;
  repos: string[];
  newTaskRepo: string;
  onNewTaskRepoChange: (repo: string) => void;
  onSubmitted: () => Promise<void>;
  onReplySubmittingChange: (target: IssueRef | null) => void;
}) {
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeStages, setActiveStages] = useState<Stage[] | null>(null);
  const [activeDispatch, setActiveDispatch] = useState<Dispatch | null>(null);
  const [polledStage, setPolledStage] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const newRepo = newTaskRepo || repos[0] || "";
  const isReply = mode === "reply";

  function stopPolling() {
    if (pollTimer.current !== null) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }

  // 送信開始時に呼ぶ。progressIdを発行し、サーバのon_stageコールバックが実際に
  // 完了させた段階（orchestrator/orchestrator/server.py の ProgressStore）を
  // /api/progress からポーリングして反映する。擬似的な時間経過ではなく実処理に
  // 連動させるための仕組み。
  function startStages(stages: Stage[]): string {
    stopPolling();
    const progressId = randomProgressId();
    setActiveStages(stages);
    setPolledStage(null);
    pollTimer.current = setInterval(() => {
      fetchProgress(progressId)
        .then((res) => setPolledStage(res.stage))
        .catch(() => {});
    }, PROGRESS_POLL_INTERVAL_MS);
    return progressId;
  }

  function endStages() {
    stopPolling();
    setActiveStages(null);
    setActiveDispatch(null);
    setPolledStage(null);
  }

  useEffect(() => stopPolling, []);

  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setMessage("");
      setTitle("");
      setPrompt("");
      setError(null);
    }
  }

  function handleSendReply() {
    if (!replyTarget) return;
    if (!message.trim()) return;
    setSubmitting(true);
    setError(null);
    const progressId = startStages(REPLY_STAGES);
    const action: InstructAction = "instruct";
    const target = replyTarget;
    onReplySubmittingChange(target);
    postInstruct(target.repo, target.number, action, message.trim(), progressId)
      .then(() => {
        onClearReplyTarget();
        onClose();
        return onSubmitted();
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "送信に失敗しました"),
      )
      .finally(() => {
        setSubmitting(false);
        onReplySubmittingChange(null);
        endStages();
      });
  }

  function handleCreateTask(dispatch: Dispatch) {
    if (!newRepo || !title.trim() || !prompt.trim()) return;
    setSubmitting(true);
    setError(null);
    setActiveDispatch(dispatch);
    const progressId = startStages(
      dispatch === "immediate" ? CREATE_IMMEDIATE_STAGES : CREATE_QUEUED_STAGES,
    );
    postCreateIssue(newRepo, title.trim(), prompt.trim(), dispatch, progressId)
      .then(() => {
        onClose();
        return onSubmitted();
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "作成に失敗しました"),
      )
      .finally(() => {
        setSubmitting(false);
        endStages();
      });
  }

  // ポーリングで得た実際の完了ステップ（polledStage）から、表示すべき段階の
  // インデックスを導出する。まだ何も報告されていなければ先頭の段階を進行中として
  // 表示し、報告済みの段階までは完了扱いにする。
  const stageIndex = activeStages
    ? Math.min(
        activeStages.length - 1,
        Math.max(0, activeStages.findIndex((s) => s.key === polledStage) + 1),
      )
    : 0;

  if (!open) {
    return (
      <button
        type="button"
        className={styles.trigger}
        onClick={onOpen}
        aria-label="新しい指示を送る"
      >
        <svg
          width="19"
          height="19"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.1"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={styles.triggerIcon}
        >
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
        </svg>
        <span className={styles.triggerLabel}>新しい指示を送る</span>
      </button>
    );
  }

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} />
      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <div className={styles.panelTitle}>
            <span className={styles.panelTitleIcon}>
              {isReply ? (
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
              ) : (
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
                  <path d="M12 5v14M5 12h14" />
                </svg>
              )}
            </span>
            {isReply ? "既存issueへ返信" : "新規タスク作成"}
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            title="閉じる"
            aria-label="閉じる"
          >
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
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {isReply ? (
          <div className={styles.body}>
            {replyTarget ? (
              <span className={styles.targetChip}>
                <svg
                  width="13"
                  height="13"
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
                {shortRepoName(replyTarget.repo)} #{replyTarget.number}
                <span className={styles.targetChipSuffix}>へ指示</span>
                <button
                  type="button"
                  onClick={onClearReplyTarget}
                  aria-label="対象issueを解除"
                >
                  ×
                </button>
              </span>
            ) : (
              <div className={styles.noTarget}>
                判断待ち一覧や活動ログの各アイテムにある「返信」から、対象のissueを選んでください。
              </div>
            )}
            <textarea
              className={styles.textarea}
              placeholder="追加の指示を入力…（例: この方針で進めて／まずテストを追加して）"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={submitting || !replyTarget}
            />
            <div className={styles.sendRow}>
              <button
                type="button"
                className={styles.sendBtn}
                onClick={handleSendReply}
                disabled={submitting || !replyTarget || !message.trim()}
              >
                {submitting ? (
                  <SpinnerIcon />
                ) : (
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
                    <path d="M22 2 11 13" />
                    <path d="M22 2 15 22l-4-9-9-4Z" />
                  </svg>
                )}
                {submitting ? "送信中…" : "指示を送信"}
              </button>
            </div>
            {submitting && activeStages && (
              <StageList stages={activeStages} stageIndex={stageIndex} />
            )}
          </div>
        ) : (
          <div className={styles.body}>
            <div>
              <div className={styles.fieldLabel}>対象プロジェクト</div>
              <select
                className={styles.select}
                value={newRepo}
                onChange={(e) => onNewTaskRepoChange(e.target.value)}
              >
                {repos.map((repo) => (
                  <option key={repo} value={repo}>
                    {shortRepoName(repo)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div className={styles.fieldLabel}>タイトル</div>
              <input
                className={styles.input}
                placeholder="例: 請求書の合計金額バリデーションを追加"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={submitting}
              />
            </div>
            <div className={styles.promptField}>
              <div className={styles.fieldLabel}>指示内容 / プロンプト</div>
              <textarea
                className={`${styles.textarea} ${styles.textareaPrompt}`}
                placeholder="AIエージェントへの具体的な指示を入力…（例: 合計金額が明細の和と一致するか検証し、不一致なら警告を出す）"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                disabled={submitting}
              />
            </div>
            <div className={styles.dispatchRow}>
              <button
                type="button"
                className={`${styles.dispatchBtn} ${styles.dispatchBtnPrimary}`}
                onClick={() => handleCreateTask("immediate")}
                disabled={
                  submitting || !newRepo || !title.trim() || !prompt.trim()
                }
              >
                {submitting && activeDispatch === "immediate" ? (
                  <SpinnerIcon />
                ) : (
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
                    <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8Z" />
                  </svg>
                )}
                {submitting && activeDispatch === "immediate"
                  ? "送信中…"
                  : "今すぐ着手"}
              </button>
              <button
                type="button"
                className={styles.dispatchBtn}
                onClick={() => handleCreateTask("queued")}
                disabled={
                  submitting || !newRepo || !title.trim() || !prompt.trim()
                }
              >
                {submitting && activeDispatch === "queued" ? (
                  <SpinnerIcon />
                ) : (
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
                    <rect x="3" y="5" width="18" height="16" rx="2" />
                    <path d="M16 3v4M8 3v4M3 11h18M9 15l2 2 4-4" />
                  </svg>
                )}
                {submitting && activeDispatch === "queued"
                  ? "送信中…"
                  : "あとで着手（todo）"}
              </button>
            </div>
            {submitting && activeStages && (
              <StageList stages={activeStages} stageIndex={stageIndex} />
            )}
          </div>
        )}
        {error && <span className={styles.error}>{error}</span>}
      </div>
    </>
  );
}
