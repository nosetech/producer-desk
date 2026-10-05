"use client";

import { useEffect, useState } from "react";
import { fetchProjectSettings, postCreateIssue, postInstruct } from "@/lib/api";
import {
  MODEL_DEFAULT,
  applyModelDirective,
  modelOptions,
} from "@/lib/modelDirective";
import { shortRepoName } from "@/lib/projectStatus";
import {
  resolveStages,
  useStageProgress,
  type StageDef,
} from "@/lib/stageProgress";
import { formatCommentTime, stripBotMarkers } from "@/lib/comment";
import type {
  Dispatch,
  InstructAction,
  IssueComment,
  ProjectSettingsResponse,
} from "@/lib/types";
import CommentBody from "./CommentBody";
import { SpinnerIcon, StageList } from "./StageProgress";
import styles from "./ComposerBar.module.css";

export interface IssueRef {
  repo: string;
  number: number;
  title: string;
  /** 返信を開いた時点の最新コメント（返信欄で読み取り専用表示する）。 */
  comment?: IssueComment;
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

function ReplyQuote({
  comment,
  openedAt,
  open,
  onToggle,
}: {
  comment: IssueComment;
  openedAt?: string;
  open: boolean;
  onToggle: () => void;
}) {
  const label = open ? "コメントを折りたたむ" : "コメントを展開";
  const summary = stripBotMarkers(comment.body).replace(/\s+/g, " ");
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
          <span className={styles.quoteHeading}>返信先のコメント</span>
          <span className={styles.quoteMeta}>
            <span className={styles.quoteAuthor}>
              {comment.author?.login ?? "unknown"}
            </span>
            <span className={styles.quoteAt}>
              {formatCommentTime(comment.createdAt)}
            </span>
          </span>
        </div>
        <a
          href={comment.url}
          target="_blank"
          rel="noreferrer"
          className={styles.quoteIconBtn}
          title="GitHubでコメントを開く"
          aria-label="GitHubでコメントを開く"
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
      {open ? (
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
      ) : (
        <div className={styles.quoteCollapsed}>{summary}</div>
      )}
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
  const [activeStages, setActiveStages] = useState<StageDef[] | null>(null);
  const [activeDispatch, setActiveDispatch] = useState<Dispatch | null>(null);
  const {
    polledStage,
    start: startProgress,
    reset: resetProgress,
  } = useStageProgress();

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
  if (replyKey !== prevReplyKey) {
    setPrevReplyKey(replyKey);
    setQuoteOpen(true);
    setReplyModel(MODEL_DEFAULT);
    setMessage((m) => applyModelDirective(m, MODEL_DEFAULT));
  }

  function endStages() {
    resetProgress();
    setActiveStages(null);
    setActiveDispatch(null);
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
      setError(null);
    }
  }

  function handleSendReply() {
    if (!replyTarget) return;
    if (!message.trim()) return;
    setSubmitting(true);
    setError(null);
    setActiveStages(REPLY_STAGES);
    const progressId = startProgress();
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
    setActiveStages(
      dispatch === "immediate" ? CREATE_IMMEDIATE_STAGES : CREATE_QUEUED_STAGES,
    );
    const progressId = startProgress();
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

  const resolvedStages = activeStages
    ? resolveStages(activeStages, polledStage, "busy")
    : null;

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
            {replyTarget?.comment && (
              <ReplyQuote
                comment={replyTarget.comment}
                openedAt={replyTarget.openedAt}
                open={quoteOpen}
                onToggle={() => setQuoteOpen((o) => !o)}
              />
            )}
            <ModelSelectRow
              value={replyModel}
              settings={replyRepo ? settingsByRepo[replyRepo] : undefined}
              disabled={submitting || !replyTarget}
              onChange={handleReplyModelChange}
            />
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
            {submitting && resolvedStages && (
              <StageList stages={resolvedStages} />
            )}
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
                disabled={submitting}
              />
            </div>
            <div className={styles.promptField}>
              <div className={styles.fieldLabel}>指示内容 / プロンプト</div>
              <div className={styles.modelRowNew}>
                <ModelSelectRow
                  value={newModel}
                  settings={settingsByRepo[newRepo]}
                  disabled={submitting}
                  onChange={handleNewModelChange}
                />
              </div>
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
            {submitting && resolvedStages && (
              <StageList stages={resolvedStages} />
            )}
          </div>
        )}
        {error && <span className={styles.error}>{error}</span>}
      </div>
    </>
  );
}
