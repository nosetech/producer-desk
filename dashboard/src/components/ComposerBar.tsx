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
  mode,
  onModeChange,
  replyTarget,
  onClearReplyTarget,
  onSelectReplyTarget,
  issues,
  repos,
  newTaskRepo,
  onNewTaskRepoChange,
  onSubmitted,
}: {
  mode: ComposerMode;
  onModeChange: (mode: ComposerMode) => void;
  replyTarget: IssueRef | null;
  onClearReplyTarget: () => void;
  onSelectReplyTarget: (target: IssueRef) => void;
  issues: IssueRef[];
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

  function issueKey(issue: IssueRef): string {
    return `${issue.repo}#${issue.number}`;
  }

  function handleSelectReply(key: string) {
    const found = issues.find((i) => issueKey(i) === key);
    if (found) onSelectReplyTarget(found);
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
        setMessage("");
        onClearReplyTarget();
        onSubmitted();
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
        setTitle("");
        setPrompt("");
        onSubmitted();
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "作成に失敗しました"),
      )
      .finally(() => setSubmitting(false));
  }

  return (
    <div className={styles.bar}>
      <div className={styles.tabs}>
        <button
          type="button"
          className={`${styles.tab} ${mode === "reply" ? styles.tabActive : ""}`}
          onClick={() => onModeChange("reply")}
        >
          既存issueへの返信
        </button>
        <button
          type="button"
          className={`${styles.tab} ${mode === "new" ? styles.tabActive : ""}`}
          onClick={() => onModeChange("new")}
        >
          新規タスク作成
        </button>
      </div>

      {mode === "reply" ? (
        <>
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
            <select
              className={styles.select}
              value=""
              onChange={(e) => handleSelectReply(e.target.value)}
            >
              <option value="" disabled>
                返信先のissueを選択…
              </option>
              {issues.map((issue) => (
                <option key={issueKey(issue)} value={issueKey(issue)}>
                  {shortRepoName(issue.repo)} #{issue.number} {issue.title}
                </option>
              ))}
            </select>
          )}
          <div className={styles.row}>
            <textarea
              className={styles.textarea}
              placeholder="issueに指示を送る…"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={submitting || !replyTarget}
            />
            <button
              type="button"
              className={styles.sendBtn}
              onClick={handleSendReply}
              disabled={submitting || !replyTarget || !message.trim()}
            >
              送信
            </button>
          </div>
        </>
      ) : (
        <>
          <div className={styles.newTaskFields}>
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
            <input
              className={styles.input}
              placeholder="タイトル"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={submitting}
            />
          </div>
          <textarea
            className={styles.textarea}
            placeholder="指示内容（プロンプト）"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={submitting}
          />
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
        </>
      )}
      {error && <span className={styles.error}>{error}</span>}
    </div>
  );
}
