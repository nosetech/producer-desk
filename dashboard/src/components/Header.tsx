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
      <div className={styles.avatar}>
        <svg
          width="24"
          height="24"
          viewBox="0 0 48 48"
          fill="none"
          aria-hidden="true"
        >
          <rect
            x="3"
            y="3"
            width="42"
            height="42"
            rx="6"
            fill="#fff"
            opacity=".22"
          />
          <rect x="8" y="9" width="15" height="12" rx="2.5" fill="#fff" />
          <rect
            x="27"
            y="9"
            width="12"
            height="17"
            rx="2.5"
            fill="#fff"
            opacity=".8"
          />
          <rect
            x="8"
            y="26"
            width="12"
            height="13"
            rx="2.5"
            fill="#fff"
            opacity=".8"
          />
          <rect x="25" y="32" width="14" height="7" rx="2.5" fill="#fff" />
        </svg>
      </div>
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
