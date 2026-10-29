"use client";

import { useEffect, useRef, useState } from "react";
import { formatCommentTime } from "@/lib/comment";
import { formatRelativeTime } from "@/lib/time";
import type { IssueComment } from "@/lib/types";
import { usePersistedSize } from "@/lib/usePersistedSize";
import CommentBody from "./CommentBody";
import styles from "./CommentViewer.module.css";

function ChevronIcon({ up }: { up: boolean }) {
  return (
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
      <path d={up ? "m18 15-6-6-6 6" : "m6 9 6 6 6-6"} />
    </svg>
  );
}

function ExternalIcon() {
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
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <path d="M15 3h6v6M10 14 21 3" />
    </svg>
  );
}

/** カードの「全文を表示」から開く、AIコメント全文のモーダル。 */
export default function CommentViewer({
  comments,
  label,
  kindLabel,
  title,
  onClose,
  onReply,
  replyDisabled,
}: {
  /** 表示候補のコメント一覧（古い→新しい順、初期表示は末尾）。 */
  comments: IssueComment[];
  /** 例: `invoice-parser #142` */
  label: string;
  kindLabel: string;
  title: string;
  onClose: () => void;
  onReply: () => void;
  replyDisabled?: boolean;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  // リサイズのドラッグをダイアログ外で離しても閉じないよう、押下がオーバーレイ上で始まったときだけ閉じる。
  const pressedOverlay = useRef(false);
  const resizeDialogRef = usePersistedSize("commentViewer", ["width"]);
  const bodyRef = usePersistedSize("commentViewer", ["height"]);
  const total = comments.length;
  // 表示中のコメント。null は末尾（直近）を表す。
  const [pickedIndex, setPickedIndex] = useState<number | null>(null);
  const index = Math.min(pickedIndex ?? total - 1, total - 1);
  const comment = comments[index];

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, [onClose]);

  return (
    <div
      className={styles.overlay}
      onMouseDown={(e) => {
        pressedOverlay.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (pressedOverlay.current && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={(el) => {
          dialogRef.current = el;
          resizeDialogRef(el);
        }}
        tabIndex={-1}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-label="AIコメント全文"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.header}>
          <span className={styles.aiBadge}>AI</span>
          <div className={styles.headerText}>
            <div className={styles.headerMeta}>
              <span className={styles.label}>{label}</span>
              <span className={styles.kind}>{kindLabel}</span>
            </div>
            <div className={styles.title}>{title}</div>
          </div>
          <button
            type="button"
            className={styles.closeX}
            onClick={onClose}
            title="閉じる（Esc）"
            aria-label="閉じる"
          >
            <svg
              width="16"
              height="16"
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
        <div className={styles.meta}>
          <span className={styles.avatar} />
          <span className={styles.author}>
            {comment.author?.login ?? "unknown"}
          </span>
          <span className={styles.at}>
            {formatCommentTime(comment.createdAt)}
          </span>
          <span className={styles.ago}>
            {formatRelativeTime(comment.createdAt)}
          </span>
          <span className={styles.spacer} />
          {total > 1 && (
            <div className={styles.nav}>
              <button
                type="button"
                className={styles.navBtn}
                onClick={() => setPickedIndex(index - 1)}
                disabled={index <= 0}
                title="前（古い）のコメント"
                aria-label="前（古い）のコメント"
              >
                <ChevronIcon up />
              </button>
              <span className={styles.navCount}>
                {index + 1} / {total}件目
              </span>
              <button
                type="button"
                className={styles.navBtn}
                onClick={() => setPickedIndex(index + 1)}
                disabled={index >= total - 1}
                title="次（新しい）のコメント"
                aria-label="次（新しい）のコメント"
              >
                <ChevronIcon up={false} />
              </button>
            </div>
          )}
          <a
            href={comment.url}
            target="_blank"
            rel="noreferrer"
            className={styles.ghLink}
          >
            GitHubで開く
            <ExternalIcon />
          </a>
        </div>
        <div ref={bodyRef} className={styles.body}>
          <CommentBody body={comment.body} size="viewer" />
        </div>
        <div className={styles.footer}>
          <span className={styles.escHint}>
            <span className={styles.kbd}>Esc</span>で閉じる
          </span>
          <span className={styles.spacer} />
          <button type="button" className={styles.closeBtn} onClick={onClose}>
            閉じる
          </button>
          <button
            type="button"
            className={styles.replyBtn}
            onClick={onReply}
            disabled={replyDisabled}
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
              <path d="M9 17 4 12l5-5" />
              <path d="M4 12h11a5 5 0 0 1 0 10" />
            </svg>
            このコメントに返信
          </button>
        </div>
      </div>
    </div>
  );
}
