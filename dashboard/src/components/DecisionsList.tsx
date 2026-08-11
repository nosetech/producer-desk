import type { IssueSummary } from "@/lib/types";
import DecisionCard from "./DecisionCard";
import styles from "./DecisionsList.module.css";

export default function DecisionsList({
  decisions,
  onApproved,
  onReply,
  onToast,
}: {
  decisions: IssueSummary[];
  onApproved: () => Promise<void>;
  onReply: (repo: string, issueNumber: number, title: string) => void;
  onToast: (text: string) => void;
}) {
  return (
    <div className={styles.panel}>
      <div className={styles.headerRow}>
        <div className={styles.headerLeft}>
          <span className={styles.title}>判断待ち</span>
          <span className={styles.countBadge}>{decisions.length} 件</span>
        </div>
      </div>
      <span className={styles.subtitle}>AIからの承認リクエスト</span>
      {decisions.length === 0 ? (
        <div className={styles.empty}>判断待ちはありません</div>
      ) : (
        <div className={styles.list}>
          {decisions.map((decision) => (
            <DecisionCard
              key={`${decision.repo}#${decision.number}`}
              decision={decision}
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
