"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { DashboardIcon, IssuesIcon, WarningIcon } from "./Icons";
import styles from "./Sidebar.module.css";

const DEFAULT_WIDTH = 208;
const MIN_WIDTH = 180;
const MAX_WIDTH = 360;
const COLLAPSED_WIDTH = 68;
const HOVER_OPEN_DELAY_MS = 140;
const HOVER_CLOSE_DELAY_MS = 220;
const STORAGE_KEY = "sidebar";

export const ISSUES_NAV_HREF = "/projects";

interface Props {
  attentionCount: number;
  anyOrphan: boolean;
}

/**
 * PC幅のサイドバー（モバイル幅ではCSSで非表示にし、BottomNavが代わりに表示される）。
 * 折りたたみ時はアイコンのみ表示し、マウスオーバーで一時的に展開する。
 * 幅はドラッグで変更できる（ダブルクリックで初期幅）。
 */
export default function Sidebar({ attentionCount, anyOrphan }: Props) {
  const pathname = usePathname();
  const onIssues = pathname.startsWith("/projects");
  const onDashboard = !onIssues;

  const [pinnedCollapsed, setPinnedCollapsed] = useState(false);
  const [hover, setHover] = useState(false);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [dragging, setDragging] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const slotRef = useRef<HTMLDivElement>(null);
  const widthRef = useRef(width);
  widthRef.current = width;

  // 保存済みの設定を復元する（SSRとの不一致を避けるためマウント後に読む）。
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
      if (typeof saved.collapsed === "boolean")
        setPinnedCollapsed(saved.collapsed);
      if (typeof saved.width === "number")
        setWidth(Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, saved.width)));
    } catch {}
  }, []);

  useEffect(() => {
    if (dragging) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ collapsed: pinnedCollapsed, width }),
      );
    } catch {}
  }, [pinnedCollapsed, width, dragging]);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const peek = pinnedCollapsed && hover;
  const collapsed = pinnedCollapsed && !hover;
  const sidebarWidth = collapsed ? COLLAPSED_WIDTH : width;

  function clearTimer() {
    if (timer.current) clearTimeout(timer.current);
  }

  function handleEnter() {
    clearTimer();
    if (!pinnedCollapsed || hover) return;
    timer.current = setTimeout(() => setHover(true), HOVER_OPEN_DELAY_MS);
  }

  function handleLeave() {
    clearTimer();
    if (dragging || !hover) return;
    timer.current = setTimeout(() => setHover(false), HOVER_CLOSE_DELAY_MS);
  }

  function handleToggle() {
    clearTimer();
    setPinnedCollapsed((c) => !c);
    setHover(false);
  }

  function handleResizeStart(e: React.MouseEvent) {
    if (e.button !== 0) return;
    e.preventDefault();
    const x0 = e.clientX;
    const w0 = widthRef.current;
    clearTimer();
    setDragging(true);
    const move = (ev: MouseEvent) =>
      setWidth(
        Math.max(
          MIN_WIDTH,
          Math.min(MAX_WIDTH, Math.round(w0 + ev.clientX - x0)),
        ),
      );
    const up = (ev: MouseEvent) => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      const rect = slotRef.current?.getBoundingClientRect();
      const outside =
        !rect ||
        ev.clientX > rect.left + widthRef.current + 4 ||
        ev.clientY < rect.top ||
        ev.clientY > rect.bottom;
      setDragging(false);
      if (outside) setHover(false);
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  const toggleLabel = pinnedCollapsed
    ? "サイドバーを常に表示する"
    : "サイドバーを折りたたむ（マウスオーバーで一時表示）";
  const itemClass = (active: boolean) =>
    `${styles.navItem} ${active ? styles.navItemActive : ""} ${collapsed ? styles.navItemCollapsed : ""}`;

  return (
    <div
      ref={slotRef}
      className={styles.slot}
      style={{
        width: pinnedCollapsed ? COLLAPSED_WIDTH : width,
        transition: dragging ? "none" : undefined,
      }}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      <aside
        className={`${styles.sidebar} ${peek ? styles.sidebarPeek : ""} ${collapsed ? styles.sidebarCollapsed : ""}`}
        style={{
          width: sidebarWidth,
          transition: dragging ? "none" : undefined,
        }}
        aria-label="メインナビゲーション"
      >
        <nav className={styles.nav}>
          <Link
            href="/"
            className={itemClass(onDashboard)}
            title="ダッシュボード"
            aria-current={onDashboard ? "page" : undefined}
          >
            <DashboardIcon size={18} />
            {!collapsed && (
              <>
                <span className={styles.navLabel}>ダッシュボード</span>
                <span
                  className={styles.navCount}
                  title="判断待ち・レビュー待ち"
                >
                  {attentionCount}
                </span>
              </>
            )}
            {collapsed && <span className={styles.attentionDot} />}
          </Link>
          <Link
            href={ISSUES_NAV_HREF}
            className={itemClass(onIssues)}
            title="issue一覧"
            aria-current={onIssues ? "page" : undefined}
          >
            <IssuesIcon size={18} />
            {!collapsed && (
              <>
                <span className={styles.navLabel}>issue一覧</span>
                {anyOrphan && (
                  <span
                    className={styles.orphanIcon}
                    title="停止している可能性があるissueがあります"
                  >
                    <WarningIcon size={13} />
                  </span>
                )}
              </>
            )}
            {collapsed && anyOrphan && (
              <span className={styles.orphanIconCollapsed}>
                <WarningIcon size={11} />
              </span>
            )}
          </Link>
        </nav>
        <div className={styles.spacer} />
        <div className={styles.foot}>
          <button
            type="button"
            className={`${styles.footBtn} ${collapsed ? styles.footBtnCollapsed : ""}`}
            onClick={handleToggle}
            title={toggleLabel}
            aria-label={toggleLabel}
            aria-expanded={!collapsed}
          >
            <svg
              width="17"
              height="17"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ flex: "none" }}
            >
              <rect x="3" y="4" width="18" height="16" rx="2.5" />
              <path
                d={
                  pinnedCollapsed
                    ? "M9 4v16M14 10l2 2-2 2"
                    : "M9 4v16M16 10l-2 2 2 2"
                }
              />
            </svg>
            {!collapsed && (
              <span className={styles.footLabel}>
                {pinnedCollapsed ? "常に表示する" : "折りたたむ"}
              </span>
            )}
          </button>
        </div>
      </aside>
      {!collapsed && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="サイドバーの幅を変更"
          aria-valuenow={width}
          aria-valuemin={MIN_WIDTH}
          aria-valuemax={MAX_WIDTH}
          title="ドラッグで幅を変更（ダブルクリックで初期幅）"
          className={styles.handle}
          style={{ left: sidebarWidth - 4 }}
          onMouseDown={handleResizeStart}
          onDoubleClick={() => setWidth(DEFAULT_WIDTH)}
        >
          <span
            className={styles.handleLine}
            style={{ background: dragging ? "var(--accent-blue)" : undefined }}
          />
        </div>
      )}
    </div>
  );
}
