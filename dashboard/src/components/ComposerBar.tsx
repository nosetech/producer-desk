"use client";

import { useState } from "react";
import { postCreateIssue, postInstruct } from "@/lib/api";
import { shortRepoName } from "@/lib/projectStatus";
import type { Dispatch, InstructAction } from "@/lib/types";
import styles from "./ComposerBar.module.css";

export interface IssueRef {
  repo: string;
  number: number;
  title: string;
}

export type ComposerMode = "reply" | "new";

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
  onSubmitted: () => void;
}) {
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const newRepo = newTaskRepo || repos[0] || "";
  const isReply = mode === "reply";

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
    const action: InstructAction = "instruct";
    postInstruct(replyTarget.repo, replyTarget.number, action, message.trim())
      .then(() => {
        onClearReplyTarget();
        onSubmitted();
        onClose();
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "送信に失敗しました"),
      )
      .finally(() => setSubmitting(false));
  }

  function handleCreateTask(dispatch: Dispatch) {
    if (!newRepo || !title.trim() || !prompt.trim()) return;
    setSubmitting(true);
    setError(null);
    postCreateIssue(newRepo, title.trim(), prompt.trim(), dispatch)
      .then(() => {
        onSubmitted();
        onClose();
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "作成に失敗しました"),
      )
      .finally(() => setSubmitting(false));
  }

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
              指示を送信
            </button>
          </div>
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
          <div>
            <div className={styles.fieldLabel}>指示内容 / プロンプト</div>
            <textarea
              className={styles.textarea}
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
              今すぐ着手
            </button>
            <button
              type="button"
              className={styles.dispatchBtn}
              onClick={() => handleCreateTask("queued")}
              disabled={
                submitting || !newRepo || !title.trim() || !prompt.trim()
              }
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
                <rect x="3" y="5" width="18" height="16" rx="2" />
                <path d="M16 3v4M8 3v4M3 11h18M9 15l2 2 4-4" />
              </svg>
              あとで着手（todo）
            </button>
          </div>
        </div>
      )}
      {error && <span className={styles.error}>{error}</span>}
    </div>
  );
}
