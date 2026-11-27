"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type ReactNode,
} from "react";
import {
  ATTACH_ACCEPT,
  ATTACH_DROP_SUB,
  ATTACH_HINT,
  addFiles,
  encodeAttachments,
  formatSize,
  namePastedFile,
  totalSize,
  type AttachError,
  type AttachItem,
  type AttachmentPayload,
} from "@/lib/mediaAttach";
import type { StageDef } from "@/lib/stageProgress";
import ImageLightbox from "./ImageLightbox";
import styles from "./MediaAttach.module.css";

// 返信欄・新規タスク作成（手動入力）の画像・動画の添付（issue #301）。
// デザイン: feature/issue-301-media-attach（`.attach.dc.html`の子コンポーネントと`.logic.js`の`_atView`）。

function hasFiles(e: DragEvent): boolean {
  return Array.from(e.dataTransfer?.types ?? []).includes("Files");
}

export interface MediaAttachState {
  items: AttachItem[];
  errors: AttachError[];
  drag: boolean;
  /** base64化（アップロード準備）の完了件数。null は送信準備中でない。 */
  uploadDone: number | null;
  addFiles: (files: File[]) => void;
  remove: (id: string) => void;
  clearErrors: () => void;
  setDrag: (drag: boolean) => void;
  /** 添付をbase64にする（進捗を表示しながら）。 */
  encode: () => Promise<AttachmentPayload[]>;
  /** 送信の受付後にトレイを空にする。 */
  reset: () => void;
  /** 送信準備に失敗したとき、進捗表示を閉じる（トレイは残す）。 */
  cancelUpload: () => void;
}

function revoke(items: AttachItem[]) {
  for (const x of items) if (x.previewUrl) URL.revokeObjectURL(x.previewUrl);
}

export function useMediaAttach(): MediaAttachState {
  const [items, setItems] = useState<AttachItem[]>([]);
  const [errors, setErrors] = useState<AttachError[]>([]);
  const [drag, setDrag] = useState(false);
  const [uploadDone, setUploadDone] = useState<number | null>(null);
  const seq = useRef(0);
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  });
  const uploading = uploadDone !== null;

  const add = useCallback(
    (files: File[]) => {
      if (uploading) return;
      const result = addFiles(
        itemsRef.current,
        files,
        () => `a${++seq.current}`,
      );
      setItems(result.items);
      setErrors(result.errors);
    },
    [uploading],
  );

  return {
    items,
    errors,
    drag,
    uploadDone,
    addFiles: add,
    remove: (id) => {
      if (uploading) return;
      revoke(itemsRef.current.filter((x) => x.id === id));
      setItems((xs) => xs.filter((x) => x.id !== id));
    },
    clearErrors: () => setErrors([]),
    setDrag,
    encode: async () => {
      setUploadDone(0);
      setErrors([]);
      return encodeAttachments(itemsRef.current, setUploadDone);
    },
    reset: () => {
      revoke(itemsRef.current);
      setItems([]);
      setErrors([]);
      setDrag(false);
      setUploadDone(null);
    },
    cancelUpload: () => setUploadDone(null),
  };
}

/** テキストエリアを包み、ドラッグ&ドロップ・貼り付けで添付を受け付ける。 */
export function AttachDropZone({
  state,
  disabled,
  children,
}: {
  state: MediaAttachState;
  disabled?: boolean;
  children: ReactNode;
}) {
  const off = disabled || state.uploadDone !== null;
  return (
    <div
      className={styles.dropWrap}
      onDragEnter={(e) => {
        if (!off && hasFiles(e)) {
          e.preventDefault();
          if (!state.drag) state.setDrag(true);
        }
      }}
      onDragOver={(e) => {
        if (!off && hasFiles(e)) {
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
        }
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null))
          state.setDrag(false);
      }}
      onDrop={(e) => {
        if (e.dataTransfer?.files?.length) {
          e.preventDefault();
          state.setDrag(false);
          if (!off) state.addFiles(Array.from(e.dataTransfer.files));
        }
      }}
      onPaste={(e: ClipboardEvent<HTMLDivElement>) => {
        const files = Array.from(e.clipboardData?.files ?? []);
        if (files.length && !off) {
          e.preventDefault();
          const now = new Date();
          state.addFiles(files.map((f) => namePastedFile(f, now)));
        }
      }}
    >
      {children}
      {state.drag && (
        <div aria-hidden="true" className={styles.dropOverlay}>
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 15V3M7 8l5-5 5 5" />
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          </svg>
          <span className={styles.dropTitle}>ここにドロップして添付</span>
          <span className={styles.dropSub}>{ATTACH_DROP_SUB}</span>
        </div>
      )}
    </div>
  );
}

function Spinner({ color, size }: { color: string; size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 42 42"
      className={styles.spin}
      style={{ color }}
    >
      <circle
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        opacity=".26"
      />
      <circle
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray="34 200"
        className={styles.spinDash}
      />
    </svg>
  );
}

function AttachThumb({
  item,
  disabled,
  onPreview,
}: {
  item: AttachItem;
  disabled: boolean;
  onPreview: (src: string) => void;
}) {
  const src = item.previewUrl;
  if (item.kind !== "image" || !src)
    return (
      <span aria-hidden="true" className={styles.vidBox}>
        <svg
          width="17"
          height="17"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="2.5" y="5" width="14" height="14" rx="2.5" />
          <path d="m16.5 10 5-3v10l-5-3" />
        </svg>
      </span>
    );
  return (
    <button
      type="button"
      className={styles.thumbBtn}
      onClick={() => onPreview(src)}
      disabled={disabled}
      aria-label={`${item.name} を拡大表示`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- ローカルのobject URL */}
      <img src={src} alt="" className={styles.thumbImg} />
    </button>
  );
}

/** 添付ボタン・添付トレイ・エラー・送信準備の進捗。テキストエリアの下に置く。 */
export default function MediaAttach({
  state,
  disabled,
  stages,
}: {
  state: MediaAttachState;
  disabled?: boolean;
  /** 送信準備の進捗で「添付をアップロード」の後に並べる段階（返信・新規作成）。 */
  stages: StageDef[];
}) {
  const { items, errors, uploadDone } = state;
  const uploading = uploadDone !== null;
  const off = disabled || uploading;
  const total = totalSize(items);
  const [preview, setPreview] = useState<{ src: string; alt: string } | null>(
    null,
  );

  return (
    <div className={styles.wrap}>
      <div className={styles.bar}>
        <label
          title="画像・動画を添付"
          className={`${styles.btn} ${off ? styles.btnOff : ""}`}
        >
          <input
            type="file"
            multiple
            accept={ATTACH_ACCEPT}
            disabled={off}
            aria-label="画像・動画を添付"
            className={styles.fileInput}
            onChange={(e) => {
              state.addFiles(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.1"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            style={{ flex: "none" }}
          >
            <path d="m21.4 11.1-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5" />
          </svg>
          画像・動画を添付
        </label>
        <span className={styles.hint}>{ATTACH_HINT}</span>
        {items.length > 0 && (
          <span aria-live="polite" className={styles.sum}>
            {items.length}件・{formatSize(total)} / 50MB
          </span>
        )}
      </div>
      {items.length > 0 && (
        <ul aria-label="添付するファイル" className={styles.tray}>
          {items.map((it, i) => {
            const upDone = uploading && i < uploadDone;
            const upCur = uploading && i === uploadDone;
            return (
              <li
                key={it.id}
                className={`${styles.chip} ${off ? styles.chipOff : ""}`}
              >
                <AttachThumb
                  item={it}
                  disabled={off}
                  onPreview={(src) => setPreview({ src, alt: it.name })}
                />
                <span className={styles.meta}>
                  <span title={it.name} className={styles.name}>
                    {it.name}
                  </span>
                  <span className={styles.sub}>
                    {upCur && <span className={styles.upDot} />}
                    {upDone && (
                      <svg
                        width="11"
                        height="11"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="var(--accent-green)"
                        strokeWidth="3"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                        style={{ flex: "none" }}
                      >
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    )}
                    {it.kind === "video" ? "動画" : "画像"} ·{" "}
                    {formatSize(it.size)}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => state.remove(it.id)}
                  disabled={off}
                  aria-label={`${it.name} を添付から外す`}
                  title="添付から外す"
                  className={styles.rmBtn}
                >
                  <svg
                    width="13"
                    height="13"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M18 6 6 18M6 6l12 12" />
                  </svg>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {errors.length > 0 && (
        <div role="alert" className={styles.errBox}>
          <div className={styles.errHeadRow}>
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              style={{ flex: "none" }}
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8v4M12 16h.01" />
            </svg>
            <span>{errors.length}件を添付できませんでした</span>
            <button
              type="button"
              onClick={state.clearErrors}
              aria-label="エラーを閉じる"
              className={styles.errClose}
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
          <ul className={styles.errList}>
            {errors.map((er, i) => (
              <li key={i}>
                <span className={styles.errName}>{er.name}</span>: {er.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {uploading && (
        <div role="status" aria-live="polite" className={styles.upBox}>
          <div className={styles.upTop}>
            <Spinner color="var(--accent-blue)" size={14} />
            <span className={styles.upHead}>添付をアップロード中</span>
            <span className={styles.upCount}>1 / {stages.length + 1}</span>
          </div>
          <div className={styles.upRows}>
            <div className={styles.upRow}>
              <Spinner color="var(--accent-green)" size={15} />
              <span className={`${styles.upLabel} ${styles.upLabelActive}`}>
                添付をアップロード
              </span>
              <span className={styles.upLine} />
              <span className={styles.upNote}>
                {uploadDone} / {items.length}件 · {formatSize(total)}
              </span>
            </div>
            {stages.map((s) => (
              <div key={s.key} className={styles.upRow}>
                <span className={styles.pendingDot} />
                <span className={styles.upLabel}>{s.label}</span>
                <span className={styles.upLine} />
                <span className={styles.upNote}>{s.note}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {preview && (
        <ImageLightbox
          src={preview.src}
          alt={preview.alt}
          href={preview.src}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}
