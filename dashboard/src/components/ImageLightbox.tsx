"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import styles from "./ImageLightbox.module.css";

/**
 * 添付画像の拡大表示（ライトボックス）。画面全体にオーバーレイして画像を表示する。
 * - portalでbody直下に描画し、親モーダルのoverflowの影響を受けない
 * - Escはcaptureフェーズで拾い、親のCommentViewer（windowのkeydown）へ伝播させない
 * - 開いている間は背景スクロールを固定し、閉じたら元の要素へフォーカスを戻す
 */
export default function ImageLightbox({
  src,
  alt,
  href,
  onClose,
}: {
  src: string;
  alt: string;
  /** 「元の大きさで開く」リンク先（新規タブ） */
  href: string;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.stopImmediatePropagation();
      e.preventDefault();
      onCloseRef.current();
    }
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = prevOverflow;
      previous?.focus?.();
    };
  }, []);

  const label = alt || "添付画像";
  return createPortal(
    <div
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label={`画像の拡大表示: ${label}`}
      onClick={(e) => {
        // portalでもReactのイベントは親ツリーへ伝播するため、親モーダルの背景クリックを発火させない
        e.stopPropagation();
        onClose();
      }}
    >
      <button
        ref={closeRef}
        type="button"
        className={styles.closeBtn}
        aria-label="閉じる（Esc）"
        title="閉じる（Esc）"
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      </button>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className={styles.image}
        src={src}
        alt={alt}
        onClick={(e) => e.stopPropagation()}
      />
      <div className={styles.bar} onClick={(e) => e.stopPropagation()}>
        <span className={styles.caption} title={label}>
          {label}
        </span>
        <a className={styles.link} href={href} target="_blank" rel="noreferrer">
          元の大きさで開く
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
          </svg>
        </a>
      </div>
    </div>,
    document.body,
  );
}
