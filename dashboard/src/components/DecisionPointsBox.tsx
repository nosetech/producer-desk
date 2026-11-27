import type { CardDecisions } from "@/lib/comment";
import InlineCode from "./InlineCode";
import styles from "./DecisionPointsBox.module.css";

function QuestionIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flex: "none" }}
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01" />
    </svg>
  );
}

function OptionIcon() {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flex: "none" }}
    >
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="18" r="3" />
      <path d="M6 9v6M18 15V9a3 3 0 0 0-3-3h-3" />
    </svg>
  );
}

/**
 * カード上の「判断が必要な事項」ブロック（Artifactデザイン issue-325 の decBox〜decMoreBtn）。
 * 判断待ちカード（issue #325）とレビュー待ちカード（issue #324）で共用する。
 */
export default function DecisionPointsBox({
  decisions,
  onViewFull,
}: {
  decisions: CardDecisions;
  onViewFull: () => void;
}) {
  return (
    <section
      className={styles.decBox}
      aria-label={`判断が必要な事項 ${decisions.total}件`}
    >
      <div className={styles.decHead}>
        <QuestionIcon />
        <span className={styles.decHeadLabel}>判断が必要な事項</span>
        <span className={styles.decCount}>{decisions.total}件</span>
        <span className={styles.decHeadSpacer} />
        <span className={styles.aiTag}>AI</span>
      </div>
      <ol role="list" className={styles.decList}>
        {decisions.items.map((item, i) => (
          <li key={i} className={styles.decRow}>
            <span aria-hidden="true" className={styles.decNum}>
              {i + 1}
            </span>
            <div className={styles.decItemBody}>
              <div className={styles.decText}>
                <InlineCode text={item.text} codeClassName={styles.decCode} />
              </div>
              {item.optionLine && (
                <div title={item.optionTitle} className={styles.decOpt}>
                  <OptionIcon />
                  <span className={styles.decOptText}>
                    選択肢: {item.optionLine}
                  </span>
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
      {decisions.more > 0 && (
        <button
          type="button"
          className={styles.decMoreBtn}
          onClick={onViewFull}
          aria-haspopup="dialog"
        >
          ほか {decisions.more}件を全文で確認
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
            style={{ flex: "none" }}
          >
            <path d="m9 18 6-6-6-6" />
          </svg>
        </button>
      )}
    </section>
  );
}
