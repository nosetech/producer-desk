import { parseCommentBlocks, type InlineSegment } from "@/lib/comment";
import styles from "./CommentBody.module.css";

function Segments({ segs }: { segs: InlineSegment[] }) {
  return segs.map((s, i) =>
    s.code ? (
      <code key={i} className={styles.inlineCode}>
        {s.text}
      </code>
    ) : (
      <span key={i}>{s.text}</span>
    ),
  );
}

/** コメント本文の読み取り専用レンダリング。`size`でモーダル用/返信欄用の文字サイズを切り替える。 */
export default function CommentBody({
  body,
  size,
}: {
  body: string;
  size: "viewer" | "quote";
}) {
  const blocks = parseCommentBlocks(body);
  return (
    <div className={`${styles.root} ${styles[size]}`}>
      {blocks.map((b, i) => {
        switch (b.kind) {
          case "heading":
            return (
              <div key={i} className={styles.heading}>
                {b.text}
              </div>
            );
          case "paragraph":
            return (
              <p key={i} className={styles.paragraph}>
                <Segments segs={b.segs} />
              </p>
            );
          case "list":
            return (
              <ul key={i} className={styles.list}>
                {b.items.map((it, j) => (
                  <li key={j} className={styles.listItem}>
                    <span className={styles.mark}>{it.mark}</span>
                    <span className={styles.itemText}>
                      <Segments segs={it.segs} />
                    </span>
                  </li>
                ))}
              </ul>
            );
          case "code":
            return (
              <pre key={i} className={styles.code}>
                {b.text}
              </pre>
            );
        }
      })}
    </div>
  );
}
