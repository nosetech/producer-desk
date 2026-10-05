"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { DashboardIcon, IssuesIcon, WarningIcon } from "./Icons";
import { ISSUES_NAV_HREF } from "./Sidebar";
import styles from "./BottomNav.module.css";

/** モバイル幅のボトムナビゲーション（PC幅ではCSSで非表示、サイドバーが代わりに表示される）。 */
export default function BottomNav({
  attentionCount,
  anyOrphan,
}: {
  attentionCount: number;
  anyOrphan: boolean;
}) {
  const pathname = usePathname();
  const onIssues = pathname.startsWith("/projects");
  const onDashboard = !onIssues;

  const itemClass = (active: boolean) =>
    `${styles.item} ${active ? styles.itemActive : ""}`;
  const pillClass = (active: boolean) =>
    `${styles.pill} ${active ? styles.pillActive : ""}`;

  return (
    <nav className={styles.nav} aria-label="メインナビゲーション">
      <Link
        href="/"
        className={itemClass(onDashboard)}
        aria-current={onDashboard ? "page" : undefined}
      >
        <span className={pillClass(onDashboard)}>
          <DashboardIcon size={20} />
          <span className={styles.badge}>{attentionCount}</span>
        </span>
        <span>ダッシュボード</span>
      </Link>
      <Link
        href={ISSUES_NAV_HREF}
        className={itemClass(onIssues)}
        aria-current={onIssues ? "page" : undefined}
      >
        <span className={pillClass(onIssues)}>
          <IssuesIcon size={20} />
          {anyOrphan && (
            <span className={styles.orphan}>
              <WarningIcon size={13} />
            </span>
          )}
        </span>
        <span>issue一覧</span>
      </Link>
    </nav>
  );
}
