"use client";

import { useState } from "react";
import { attachmentProxyUrl } from "@/lib/comment";
import styles from "./CommentBody.module.css";
import ImageLightbox from "./ImageLightbox";

/**
 * 添付画像。取得に失敗した場合（Privateリポジトリでトークン未設定・権限なし等、issue #268）は
 * 壊れた画像ではなく、原因と元のGitHubリンク付きのプレースホルダを表示する。
 */
export default function AttachmentImage({
  url,
  alt,
}: {
  url: string;
  alt: string;
}) {
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  if (failed) {
    return (
      <span className={styles.imageError} role="img" aria-label={alt}>
        添付画像を読み込めません
        {alt ? `（${alt}）` : ""}
        ：GitHubトークン未設定、またはリポジトリの閲覧権限がない可能性があります。{" "}
        <a className={styles.link} href={url} target="_blank" rel="noreferrer">
          GitHubで開く
        </a>
      </span>
    );
  }
  const proxied = attachmentProxyUrl(url);
  return (
    <>
      <button
        type="button"
        className={styles.zoomTrigger}
        aria-label="画像を拡大表示"
        title="クリックで拡大"
        onClick={() => setOpen(true)}
      >
        {/* 添付画像は動的なプロキシURLのため next/image の最適化対象にしない */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          className={styles.media}
          src={proxied}
          alt={alt}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      </button>
      {open && (
        <ImageLightbox
          src={proxied}
          alt={alt}
          href={proxied}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
