import ThemeToggle from "./ThemeToggle";
import styles from "./Header.module.css";
import { version } from "../../package.json";

export default function Header() {
  return (
    <header className={styles.header}>
      <div className={styles.brand}>
        <div className={styles.avatar}>
          <svg
            width="21"
            height="21"
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
          <div className={styles.titleRow}>
            <div className={styles.title}>producer-desk</div>
            <span className={styles.version}>v{version}</span>
          </div>
          <div className={styles.subtitle}>
            自走型AI開発オーケストレーション
          </div>
        </div>
      </div>
      <div className={styles.meta}>
        <ThemeToggle />
      </div>
    </header>
  );
}
