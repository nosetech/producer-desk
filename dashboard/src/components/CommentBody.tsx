import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  attachmentProxyUrl,
  splitAttachments,
  type AttachmentLine,
} from "@/lib/comment";
import styles from "./CommentBody.module.css";

const REMARK_PLUGINS = [remarkGfm];

// 添付ファイル（user-attachments/assets）以外の画像は描画しない（通常の文字列のまま見せる）
const ASSET_URL =
  /^https:\/\/github\.com\/user-attachments\/assets\/[0-9a-fA-F-]{36}$/;

const SAFE_LINK = /^https?:\/\//i;

const components: Components = {
  h1: ({ children }) => <h1 className={styles.mdH1}>{children}</h1>,
  h2: ({ children }) => <h2 className={styles.mdH2}>{children}</h2>,
  h3: ({ children }) => <h3 className={styles.mdH3}>{children}</h3>,
  h4: ({ children }) => <h4 className={styles.mdH3}>{children}</h4>,
  h5: ({ children }) => <h5 className={styles.mdH3}>{children}</h5>,
  h6: ({ children }) => <h6 className={styles.mdH3}>{children}</h6>,
  p: ({ children }) => <p className={styles.paragraph}>{children}</p>,
  ul: ({ children }) => <ul className={styles.mdList}>{children}</ul>,
  ol: ({ children }) => <ol className={styles.mdList}>{children}</ol>,
  li: ({ children }) => <li className={styles.mdItem}>{children}</li>,
  input: ({ checked }) => (
    <input
      type="checkbox"
      checked={!!checked}
      disabled
      readOnly
      className={styles.checkbox}
    />
  ),
  a: ({ href, children }) =>
    href && SAFE_LINK.test(href) ? (
      <a className={styles.link} href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
  img: ({ src, alt }) =>
    typeof src === "string" && ASSET_URL.test(src) ? (
      // 添付画像は動的なプロキシURLのため next/image の最適化対象にしない
      // eslint-disable-next-line @next/next/no-img-element
      <img
        className={styles.media}
        src={attachmentProxyUrl(src)}
        alt={alt ?? ""}
        loading="lazy"
      />
    ) : (
      <span>{alt ?? ""}</span>
    ),
  pre: ({ children }) => <pre className={styles.code}>{children}</pre>,
  code: ({ className, children }) => (
    <code
      className={
        className ? `${className} ${styles.blockCode}` : styles.inlineCode
      }
    >
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className={styles.tableWrap}>
      <table className={styles.table}>{children}</table>
    </div>
  ),
  blockquote: ({ children }) => (
    <blockquote className={styles.blockquote}>{children}</blockquote>
  ),
  hr: () => <hr className={styles.hr} />,
};

function Attachment({ item }: { item: AttachmentLine }) {
  switch (item.kind) {
    case "image":
      return (
        // 添付画像は動的なプロキシURLのため next/image の最適化対象にしない
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className={styles.media}
          src={attachmentProxyUrl(item.url)}
          alt={item.alt}
          loading="lazy"
        />
      );
    case "video":
      return (
        <video
          className={styles.media}
          src={attachmentProxyUrl(item.url)}
          controls
          preload="metadata"
        />
      );
    case "file":
      return (
        <a
          className={styles.fileLink}
          href={attachmentProxyUrl(item.url)}
          download={item.name}
        >
          {item.name}
        </a>
      );
  }
}

/** コメント本文の読み取り専用レンダリング。`size`でモーダル用/返信欄用の文字サイズを切り替える。 */
export default function CommentBody({
  body,
  size,
}: {
  body: string;
  size: "viewer" | "quote";
}) {
  return (
    <div className={`${styles.root} ${styles[size]}`}>
      {splitAttachments(body).map((seg, i) =>
        seg.kind === "markdown" ? (
          <ReactMarkdown
            key={i}
            remarkPlugins={REMARK_PLUGINS}
            components={components}
          >
            {seg.text}
          </ReactMarkdown>
        ) : (
          <Attachment key={i} item={seg} />
        ),
      )}
    </div>
  );
}
