import type { PrCandidate } from "@/lib/types";
import styles from "./PrBadge.module.css";

function PrIcon() {
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
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="18" r="3" />
      <path d="M6 9v6M18 15V9a3 3 0 0 0-3-3h-3" />
      <path d="M12 3 9 6l3 3" />
    </svg>
  );
}

function PrCandidateIcon() {
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
      style={{ flex: "none" }}
    >
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="6" r="3" />
      <path d="M6 9v6M18 9v1a2 2 0 0 1-2 2H8" />
    </svg>
  );
}

function PrNoneIcon() {
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
      style={{ flex: "none" }}
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v4M12 16h.01" />
    </svg>
  );
}

/**
 * レビュー待ちissueの対応PR表示（カード・全文表示モーダル共用）。
 * PR番号あり: `PR #n` リンク / 候補複数: `PR候補 N件` チップ / 未特定: `PR未特定` チップ。
 */
export default function PrBadge({
  repo,
  prNumber,
  candidates,
  className,
}: {
  repo: string;
  prNumber: number | null | undefined;
  candidates: PrCandidate[] | null | undefined;
  /** 配置調整用（例: モバイルでの右寄せ）。 */
  className?: string;
}) {
  const extra = className ? ` ${className}` : "";
  if (prNumber != null) {
    return (
      <a
        href={`https://github.com/${repo}/pull/${prNumber}`}
        target="_blank"
        rel="noreferrer"
        className={`${styles.prLink}${extra}`}
      >
        <PrIcon />
        PR #{prNumber}
      </a>
    );
  }
  const count = (candidates ?? []).length;
  if (count > 1) {
    return (
      <span
        className={`${styles.prCandidateChip}${extra}`}
        title="対応PRの候補が複数あります。承認時にマージするPRを選択します"
      >
        <PrCandidateIcon />
        PR候補 {count}件
      </span>
    );
  }
  return (
    <span
      className={`${styles.prNoneChip}${extra}`}
      title="このissueに対応するPRを特定できませんでした"
    >
      <PrNoneIcon />
      PR未特定
    </span>
  );
}
