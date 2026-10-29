"use client";

import { useEffect, useState } from "react";
import { fetchProjectSettings, postCreateIssue, postInstruct } from "@/lib/api";
import {
  MODEL_DEFAULT,
  applyModelDirective,
  modelOptions,
} from "@/lib/modelDirective";
import { shortRepoName } from "@/lib/projectStatus";
import type { StageDef } from "@/lib/stageProgress";
import { findIssueJob } from "@/lib/jobs";
import {
  DECISION_POINTS_HEADING,
  commentSummary,
  extractDecisionPoints,
  formatCommentTime,
} from "@/lib/comment";
import type {
  Dispatch,
  IssueComment,
  ProjectSettingsResponse,
} from "@/lib/types";
import CommentBody from "./CommentBody";
import { useApp } from "./AppContext";
import styles from "./ComposerBar.module.css";

export interface IssueRef {
  repo: string;
  number: number;
  title: string;
  /** 返信を開いた時点のコメント一覧（古い→新しい順。返信欄で読み取り専用表示し、初期表示は末尾）。 */
  comments?: IssueComment[];
  /** commentsがコメントではなくissue本文の場合true（issue #231）。 */
  isIssueBody?: boolean;
  /** 返信を開いた時点（ISO8601）。 */
  openedAt?: string;
}

export type ComposerMode = "reply" | "new";

// 実際の処理順（orchestrator/orchestrator/instruct.py の handle_instruct /
// handle_create_issue）に合わせた段階。表示中の段階は擬似進行ではなく、
// サーバがon_stageコールバックで実際に完了したタイミングをポーリングで反映する。
const REPLY_STAGES: StageDef[] = [
  { key: "comment", label: "コメントを投稿", note: "POST comment" },
  { key: "label", label: "ラベルを更新", note: "label" },
  { key: "dispatch", label: "エージェントへ引き渡し", note: "queue" },
];
const CREATE_IMMEDIATE_STAGES: StageDef[] = [
  { key: "issue", label: "issueを作成", note: "POST /issues" },
  { key: "label", label: "ラベルを付与", note: "label" },
  { key: "dispatch", label: "エージェントへ引き渡し", note: "queue" },
];
const CREATE_QUEUED_STAGES: StageDef[] = [
  { key: "issue", label: "issueを作成", note: "POST /issues" },
  { key: "label", label: "todoとして登録", note: "label" },
];

function defaultModelHint(settings: ProjectSettingsResponse | undefined) {
  return `既定: ${
    settings?.execution_mode === "litellm_proxy"
      ? `LiteLLM · ${settings.litellm_model ?? ""}`
      : "Claude Code"
  }`;
}

function ModelSelectRow({
  value,
  settings,
  disabled,
  onChange,
}: {
  value: string;
  settings: ProjectSettingsResponse | undefined;
  disabled: boolean;
  onChange: (model: string) => void;
}) {
  return (
    <div className={styles.modelRow}>
      <span className={styles.modelLabel}>
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
          <rect x="4" y="4" width="16" height="16" rx="3" />
          <path d="M9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3" />
        </svg>
        使用するモデル
      </span>
      <select
        className={styles.modelSelect}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        aria-label="使用するモデル"
      >
        {modelOptions(settings?.available_models ?? []).map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}
          </option>
        ))}
      </select>
      {value === MODEL_DEFAULT && (
        <span className={styles.modelHint}>{defaultModelHint(settings)}</span>
      )}
    </div>
  );
}

// 判断事項本文のインライン`code`をコード表示にする（Claude Designの_segsに合わせる）。
function InlineCode({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/(`[^`]+`)/)
        .filter(Boolean)
        .map((part, i) =>
          part.length > 1 && part.startsWith("`") && part.endsWith("`") ? (
            <code key={i} className={styles.decCode}>
              {part.slice(1, -1)}
            </code>
          ) : (
            <span key={i}>{part.replace(/\*\*/g, "")}</span>
          ),
        )}
    </>
  );
}

// 「Foo: 説明」形式の選択肢は、先頭（12文字以内）をタグとして分けて表示する。
function splitOptionTag(option: string): { tag: string; text: string } | null {
  const m = option.match(/^([^:：\s]{1,12})\s*[:：]\s*(.+)$/);
  return m ? { tag: m[1], text: m[2] } : null;
}

function ReplyQuote({
  comments,
  index,
  onIndexChange,
  isIssueBody,
  openedAt,
  open,
  onToggle,
}: {
  comments: IssueComment[];
  index: number;
  onIndexChange: (index: number) => void;
  isIssueBody?: boolean;
  openedAt?: string;
  open: boolean;
  onToggle: () => void;
}) {
  const comment = comments[index];
  const total = comments.length;
  const noun = isIssueBody ? "issue本文" : "コメント";
  const label = open ? `${noun}を折りたたむ` : `${noun}を展開`;
  const summary = commentSummary(comment);
  // 判断事項は返信先がコメントの場合のみ抽出する（issue本文は従来表示。issue #234）。
  const decisions = isIssueBody ? null : extractDecisionPoints(comment.body);
  // 「全文を見る」で全文表示に切り替えた対象のコメント（コメントを切り替えたら判断事項表示に戻る）。
  const commentKey = `${index}:${comment.url}`;
  const [fullKey, setFullKey] = useState<string | null>(null);
  const showFull = !decisions || fullKey === commentKey;
  const changeIndex = (next: number) => {
    setFullKey(null);
    onIndexChange(next);
  };
  const openedTime = openedAt
    ? new Date(openedAt).toLocaleTimeString("ja-JP", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;
  return (
    <div className={styles.quoteBox}>
      <div className={styles.quoteHeader}>
        <span className={styles.quoteAiTag}>AI</span>
        <div className={styles.quoteHeaderText}>
          <span className={styles.quoteHeading}>返信先の{noun}</span>
          <span className={styles.quoteMeta}>
            <span className={styles.quoteAuthor}>
              {comment.author?.login ?? "unknown"}
            </span>
            {comment.createdAt && (
              <span className={styles.quoteAt}>
                {formatCommentTime(comment.createdAt)}
              </span>
            )}
          </span>
        </div>
        {total > 1 && (
          <div className={styles.quoteNav}>
            <button
              type="button"
              className={styles.quoteIconBtn}
              onClick={() => changeIndex(index - 1)}
              disabled={index <= 0}
              title="前（古い）のコメント"
              aria-label="前（古い）のコメント"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.3"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="m18 15-6-6-6 6" />
              </svg>
            </button>
            <span className={styles.quoteNavCount}>
              {index + 1} / {total}件目
            </span>
            <button
              type="button"
              className={styles.quoteIconBtn}
              onClick={() => changeIndex(index + 1)}
              disabled={index >= total - 1}
              title="次（新しい）のコメント"
              aria-label="次（新しい）のコメント"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.3"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            </button>
          </div>
        )}
        <a
          href={comment.url}
          target="_blank"
          rel="noreferrer"
          className={styles.quoteIconBtn}
          title={`GitHubで${noun}を開く`}
          aria-label={`GitHubで${noun}を開く`}
        >
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
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <path d="M15 3h6v6M10 14 21 3" />
          </svg>
        </a>
        <button
          type="button"
          className={styles.quoteIconBtn}
          onClick={onToggle}
          title={label}
          aria-label={label}
          aria-expanded={open}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.3"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={styles.quoteChevron}
            style={{ transform: open ? "rotate(180deg)" : "none" }}
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </button>
      </div>
      {open && decisions && !showFull && (
        <>
          <div className={styles.quoteBody}>
            <div className={styles.decHeading}>
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="var(--accent-blue)"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ flex: "none" }}
              >
                <path d="M9 11l3 3 8-8" />
                <path d="M20 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
              </svg>
              <span className={styles.decTitle}>{DECISION_POINTS_HEADING}</span>
              <span className={styles.decCount}>{decisions.length}件</span>
            </div>
            <ol className={styles.decList}>
              {decisions.map((d, i) => (
                <li key={i} className={styles.decCard}>
                  <div className={styles.decMain}>
                    <span className={styles.decNum}>{i + 1}</span>
                    <span className={styles.decText}>
                      <InlineCode text={d.text} />
                    </span>
                  </div>
                  {d.options.length > 0 && (
                    <ul className={styles.decOptions} aria-label="選択肢">
                      {d.options.map((o, j) => {
                        const tagged = splitOptionTag(o);
                        return (
                          <li key={j} className={styles.decOption}>
                            {tagged ? (
                              <span className={styles.decOptionTag}>
                                {tagged.tag}
                              </span>
                            ) : (
                              <span className={styles.decBullet}>•</span>
                            )}
                            <span className={styles.decOptionText}>
                              <InlineCode text={tagged ? tagged.text : o} />
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </li>
              ))}
            </ol>
          </div>
          <div className={styles.quoteFoot}>
            <span className={styles.quoteFootNote}>
              {openedTime
                ? `${openedTime} 時点のコメントから抽出`
                : "コメントから抽出"}
            </span>
            <button
              type="button"
              className={styles.quoteFootBtn}
              onClick={() => setFullKey(commentKey)}
            >
              全文を見る
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.3"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ flex: "none" }}
              >
                <path d="m9 6 6 6-6 6" />
              </svg>
            </button>
          </div>
        </>
      )}
      {open && showFull && (
        <div className={styles.quoteBody}>
          <CommentBody body={comment.body} size="quote" />
          {openedTime && (
            <div className={styles.quoteSnapshot}>
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
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
              </svg>
              返信を開いた時点（{openedTime}）の内容を表示中
            </div>
          )}
        </div>
      )}
      {open && decisions && showFull && (
        <div className={styles.quoteFoot}>
          <button
            type="button"
            className={styles.quoteFootBtn}
            onClick={() => setFullKey(null)}
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.3"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ flex: "none" }}
            >
              <path d="m15 18-6-6 6-6" />
            </svg>
            判断事項に戻る
          </button>
          <span style={{ flex: 1 }} />
          <span className={styles.quoteFootNote} style={{ flex: "none" }}>
            {decisions.length}件の判断事項
          </span>
        </div>
      )}
      {!open && (
        <div className={styles.quoteCollapsedRow}>
          {decisions && (
            <span className={styles.decCount}>判断 {decisions.length}件</span>
          )}
          <span className={styles.quoteCollapsedText}>{summary}</span>
        </div>
      )}
    </div>
  );
}

export default function ComposerBar({
  open,
  mode,
  replyTarget,
  onClearReplyTarget,
  onClose,
  repos,
  newTaskRepo,
  onNewTaskRepoChange,
}: {
  open: boolean;
  mode: ComposerMode;
  replyTarget: IssueRef | null;
  onClearReplyTarget: () => void;
  onClose: () => void;
  repos: string[];
  newTaskRepo: string;
  onNewTaskRepoChange: (repo: string) => void;
}) {
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { jobs, startJob } = useApp();

  const [replyModel, setReplyModel] = useState(MODEL_DEFAULT);
  const [newModel, setNewModel] = useState(MODEL_DEFAULT);
  const [settingsByRepo, setSettingsByRepo] = useState<
    Record<string, ProjectSettingsResponse>
  >({});

  const newRepo = newTaskRepo || repos[0] || "";
  const isReply = mode === "reply";
  const replyRepo = replyTarget?.repo;

  // 使用モデルの選択肢（available_models）と既定値の表示用に、対象repoの設定を取得する。
  // 取得に失敗した場合は選択肢が「既定のまま」「Claude Code」のみになる（送信自体は妨げない）。
  useEffect(() => {
    const repo = isReply ? replyRepo : newRepo;
    if (!open || !repo) return;
    let cancelled = false;
    fetchProjectSettings(repo)
      .then((data) => {
        if (!cancelled)
          setSettingsByRepo((prev) => ({ ...prev, [repo]: data }));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [open, isReply, replyRepo, newRepo]);

  // ESCキーでパネルを閉じる。
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  function handleReplyModelChange(model: string) {
    setReplyModel(model);
    setMessage((m) => applyModelDirective(m, model));
  }

  function handleNewModelChange(model: string) {
    setNewModel(model);
    setPrompt((p) => applyModelDirective(p, model));
  }

  function handleNewRepoChange(repo: string) {
    // プロジェクトごとにavailable_modelsが異なるため、選択済みのモデルは破棄する。
    handleNewModelChange(MODEL_DEFAULT);
    onNewTaskRepoChange(repo);
  }

  // 返信対象のissueが変わったら、前の対象に向けた選択・自動挿入を引き継がない。
  const replyKey = replyTarget
    ? `${replyTarget.repo}#${replyTarget.number}`
    : "";
  const [prevReplyKey, setPrevReplyKey] = useState(replyKey);
  const [quoteOpen, setQuoteOpen] = useState(true);
  // 表示中の引用コメント。null は末尾（直近）を表す（返信を開き直すたびに末尾へ戻す）。
  const [quoteIndex, setQuoteIndex] = useState<number | null>(null);
  if (replyKey !== prevReplyKey) {
    setPrevReplyKey(replyKey);
    setQuoteOpen(true);
    setQuoteIndex(null);
    setReplyModel(MODEL_DEFAULT);
    setMessage((m) => applyModelDirective(m, MODEL_DEFAULT));
  }

  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setMessage("");
      setTitle("");
      setPrompt("");
      setReplyModel(MODEL_DEFAULT);
      setNewModel(MODEL_DEFAULT);
      setQuoteIndex(null);
      setError(null);
    }
  }

  // 返信先issueが他の操作を処理中の間のみ送信を止める（別issue・別プロジェクトは妨げない）。
  const replyBusy =
    replyTarget != null &&
    findIssueJob(jobs, replyTarget.repo, replyTarget.number) !== undefined;

  // 送信はバックグラウンドのジョブとして実行し、パネルは即座に閉じる（issue #212）。
  // 進捗・失敗は対象カード（カードが無い場合・新規作成はヘッダーの処理状況）に表示する。
  function handleSendReply() {
    if (!replyTarget || !message.trim()) return;
    const target = replyTarget;
    const text = message.trim();
    const accepted = startJob({
      kind: "reply",
      repo: target.repo,
      number: target.number,
      title: target.title,
      stages: REPLY_STAGES,
      exec: (progressId) =>
        postInstruct(target.repo, target.number, "instruct", text, progressId),
      successMessage: `${shortRepoName(target.repo)} #${target.number} へ指示を送信しました。`,
    });
    if (!accepted) {
      setError("このissueは別の操作を処理中です。完了後に再度お試しください。");
      return;
    }
    onClearReplyTarget();
    onClose();
  }

  function handleCreateTask(dispatch: Dispatch) {
    if (!newRepo || !title.trim() || !prompt.trim()) return;
    const repo = newRepo;
    const issueTitle = title.trim();
    const body = prompt.trim();
    startJob({
      kind: "new",
      repo,
      title: issueTitle,
      stages:
        dispatch === "immediate"
          ? CREATE_IMMEDIATE_STAGES
          : CREATE_QUEUED_STAGES,
      exec: (progressId) =>
        postCreateIssue(repo, issueTitle, body, dispatch, progressId),
      successMessage:
        dispatch === "immediate"
          ? `${shortRepoName(repo)} に新しいタスクを作成し、着手を依頼しました。`
          : `${shortRepoName(repo)} にタスクをtodoとして登録しました（あとで着手）。`,
    });
    onClose();
  }

  if (!open) return null;

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
            {replyTarget?.comments && replyTarget.comments.length > 0 && (
              <ReplyQuote
                comments={replyTarget.comments}
                index={Math.min(
                  quoteIndex ?? replyTarget.comments.length - 1,
                  replyTarget.comments.length - 1,
                )}
                onIndexChange={setQuoteIndex}
                isIssueBody={replyTarget.isIssueBody}
                openedAt={replyTarget.openedAt}
                open={quoteOpen}
                onToggle={() => setQuoteOpen((o) => !o)}
              />
            )}
            <ModelSelectRow
              value={replyModel}
              settings={replyRepo ? settingsByRepo[replyRepo] : undefined}
              disabled={replyBusy || !replyTarget}
              onChange={handleReplyModelChange}
            />
            <textarea
              className={styles.textarea}
              placeholder="追加の指示を入力…（例: この方針で進めて／まずテストを追加して）"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={replyBusy || !replyTarget}
            />
            <div className={styles.sendRow}>
              <button
                type="button"
                className={styles.sendBtn}
                onClick={handleSendReply}
                disabled={replyBusy || !replyTarget || !message.trim()}
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
                onChange={(e) => handleNewRepoChange(e.target.value)}
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
              />
            </div>
            <div className={styles.promptField}>
              <div className={styles.fieldLabel}>指示内容 / プロンプト</div>
              <div className={styles.modelRowNew}>
                <ModelSelectRow
                  value={newModel}
                  settings={settingsByRepo[newRepo]}
                  disabled={false}

                  onChange={handleNewModelChange}
                />
              </div>
              <textarea
                className={`${styles.textarea} ${styles.textareaPrompt}`}
                placeholder="AIエージェントへの具体的な指示を入力…（例: 合計金額が明細の和と一致するか検証し、不一致なら警告を出す）"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </div>
            <div className={styles.dispatchRow}>
              <button
                type="button"
                className={`${styles.dispatchBtn} ${styles.dispatchBtnPrimary}`}
                onClick={() => handleCreateTask("immediate")}
                disabled={!newRepo || !title.trim() || !prompt.trim()}
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
                disabled={!newRepo || !title.trim() || !prompt.trim()}
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
    </>
  );
}
