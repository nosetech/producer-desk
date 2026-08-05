"use client";

import { useState } from "react";
import { postCreateIssue, postInstruct } from "@/lib/api";
import { shortRepoName } from "@/lib/projectStatus";
import type { Dispatch } from "@/lib/types";
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
    if (!replyTarget || !message.trim()) return;
    setSubmitting(true);
    setError(null);
    postInstruct(
      replyTarget.repo,
      replyTarget.number,
      "instruct",
      message.trim(),
    )
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
              {shortRepoName(replyTarget.repo)} #{replyTarget.number}{" "}
              {replyTarget.title}
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
            placeholder="issueに指示を送る…"
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
              送信
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
              placeholder="タイトル"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={submitting}
            />
          </div>
          <div>
            <div className={styles.fieldLabel}>指示内容 / プロンプト</div>
            <textarea
              className={styles.textarea}
              placeholder="指示内容（プロンプト）"
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
              あとで着手（todo登録）
            </button>
          </div>
        </div>
      )}
      {error && <span className={styles.error}>{error}</span>}
    </div>
  );
}
