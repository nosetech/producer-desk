import type { IssueSummary } from "@/lib/types";
import ReviewCard from "./ReviewCard";
import styles from "./ReviewsList.module.css";

export default function ReviewsList({
  reviews,
  onApproved,
  onReply,
  onToast,
}: {
  reviews: IssueSummary[];
  onApproved: () => void;
  onReply: (repo: string, issueNumber: number, title: string) => void;
  onToast: (text: string) => void;
}) {
  return (
    <div className={styles.panel}>
      <div className={styles.headerRow}>
        <div className={styles.headerLeft}>
          <span className={styles.title}>レビュー待ち</span>
          <span
            className={`${styles.countBadge} ${reviews.length > 0 ? styles.countBadgeActive : styles.countBadgeDone}`}
          >
            {reviews.length > 0 ? `${reviews.length} 件` : "0 件"}
          </span>
        </div>
      </div>
      <span className={styles.subtitle}>PR作成済み・マージ承認待ち</span>
      {reviews.length === 0 ? (
        <div className={styles.empty}>
          <div>レビュー待ちはありません</div>
          <div className={styles.emptySub}>未マージのPRはありません。</div>
        </div>
      ) : (
        <div className={styles.list}>
          {reviews.map((review) => (
            <ReviewCard
              key={`${review.repo}#${review.number}`}
              review={review}
              onApproved={onApproved}
              onReply={onReply}
              onToast={onToast}
            />
          ))}
        </div>
      )}
    </div>
  );
}
