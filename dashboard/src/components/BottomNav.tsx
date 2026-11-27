"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  DashboardIcon,
  IssuesIcon,
  PromptIcon,
  SnippetIcon,
  WarningIcon,
} from "./Icons";
import {
  ISSUES_NAV_HREF,
  PROMPTS_NAV_HREF,
  SNIPPETS_NAV_HREF,
} from "./Sidebar";
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
  const onPrompts = pathname.startsWith(PROMPTS_NAV_HREF);
  const onSnippets = pathname.startsWith(SNIPPETS_NAV_HREF);
  const onDashboard = !onIssues && !onPrompts && !onSnippets;

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
      <Link
        href={PROMPTS_NAV_HREF}
        className={itemClass(onPrompts)}
        aria-current={onPrompts ? "page" : undefined}
      >
        <span className={pillClass(onPrompts)}>
          <PromptIcon size={20} />
        </span>
        {/* 4項目が並ぶため、デザインどおり短い表記にする（issue #323） */}
        <span>プロンプト</span>
      </Link>
      <Link
        href={SNIPPETS_NAV_HREF}
        className={itemClass(onSnippets)}
        aria-current={onSnippets ? "page" : undefined}
      >
        <span className={pillClass(onSnippets)}>
          <SnippetIcon size={20} />
        </span>
        <span>定型文</span>
      </Link>
    </nav>
  );
}
