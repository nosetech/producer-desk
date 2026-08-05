import { formatRelativeTime } from "@/lib/time";
import ThemeToggle from "./ThemeToggle";
import styles from "./Header.module.css";

export default function Header({
  decisionsCount,
  projectsCount,
  lastUpdated,
}: {
  decisionsCount: number;
  projectsCount: number;
  lastUpdated: Date | null;
}) {
  return (
    <header className={styles.header}>
      <div className={styles.avatar}>pd</div>
      <div className={styles.titleBlock}>
        <div className={styles.title}>producer-desk</div>
        <div className={styles.subtitle}>自走型AI開発オーケストレーション</div>
      </div>
      <div className={styles.meta}>
        {decisionsCount > 0 && (
          <span className={`${styles.pill} ${styles.pillDecisions}`}>
            {decisionsCount} 件の判断待ち
          </span>
        )}
        <span className={`${styles.pill} ${styles.pillNeutral}`}>
          プロジェクト {projectsCount}
        </span>
        {lastUpdated && (
          <span className={styles.updatedAt}>
            {formatRelativeTime(lastUpdated.toISOString())}に更新
          </span>
        )}
        <ThemeToggle />
      </div>
    </header>
  );
}
