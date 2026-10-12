"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { postRefreshProject } from "@/lib/api";
import {
  FILTER_ALL,
  FILTER_ORPHAN,
  buildFilterOptions,
  filterIssues,
  formatAbsoluteTime,
  isClosed,
  issueStatusKey,
  issueStatusText,
} from "@/lib/issueList";
import { shortRepoName } from "@/lib/projectStatus";
import { statusCountMeta } from "@/lib/status";
import { formatRelativeTime } from "@/lib/time";
import type { ProjectIssue } from "@/lib/types";
import { useApp } from "./AppContext";
import { ExternalLinkIcon, PlusIcon, WarningIcon } from "./Icons";
import RefreshButton from "./RefreshButton";
import SyncAgo from "./SyncAgo";
import styles from "./ProjectIssues.module.css";

const SKELETON_WIDTHS = [62, 48, 70, 40, 56, 44];

type LoadState = "loading" | "ready" | "error";
// initial: 初回表示・プロジェクト切替・エラー画面の再試行（スケルトン表示）。
// manual: 再取得ボタン（一覧を残しボタンのみ読み込み中表示、失敗はToast）。
// poll: 30秒ごとの定期更新、およびTTL超過キャッシュ表示時のバックグラウンド再取得（一覧を残し、失敗は無視）。
type FetchMode = "initial" | "manual" | "poll";

function orphanNote(updatedAt: string): string {
  const ago = formatRelativeTime(updatedAt);
  return `${ago.endsWith("前") ? ago.slice(0, -1) : ago} 進捗なし`;
}

function StatusBadge({ issue }: { issue: ProjectIssue }) {
  const key = issueStatusKey(issue);
  const meta = statusCountMeta(key);
  return (
    <span
      className={`${styles.badge} ${key === "untagged" ? styles.badgeUntagged : ""}`}
      style={{
        background: `var(${meta.bgVar})`,
        color: `var(${meta.colorVar})`,
      }}
    >
      <span className={styles.badgeDot} />
      {issueStatusText(key)}
    </span>
  );
}

function ReplyIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flex: "none" }}
      aria-hidden="true"
    >
      <path d="M9 17 4 12l5-5" />
      <path d="M4 12h11a5 5 0 0 1 0 10" />
    </svg>
  );
}

function CommentIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.1"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flex: "none" }}
      aria-hidden="true"
    >
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
    </svg>
  );
}

export default function ProjectIssues({ repo }: { repo: string }) {
  const {
    state,
    repos,
    refresh,
    showToast,
    openReply,
    openNewTask,
    lookupIssues,
    storeIssues,
    settings,
  } = useApp();
  // キャッシュ（issue #198）があればスケルトンを挟まず即時表示する。ページは`key={repo}`で
  // プロジェクトごとにマウントし直されるため、前プロジェクトの一覧が残ることはない。
  const [initialCache] = useState(() => lookupIssues(repo));
  const [load, setLoad] = useState<LoadState>(
    initialCache.kind === "miss" ? "loading" : "ready",
  );
  const [issues, setIssues] = useState<ProjectIssue[]>(
    initialCache.kind === "miss" ? [] : initialCache.entry.issues,
  );
  const [errorMessage, setErrorMessage] = useState("");
  const [filter, setFilter] = useState<string>(FILTER_ALL);
  const [showDone, setShowDone] = useState(false);
  const [sort, setSort] = useState<"desc" | "asc">("desc");
  const [refreshing, setRefreshing] = useState(false);
  const requestSeq = useRef(0);
  const restartPoll = useRef<() => void>(() => {});

  // 一覧だけでなくラベル（状態）別件数・更新時刻も最新化するため、オーケストレータの
  // プロジェクト単位再取得（issue #197）で当該リポジトリ分のStateStoreを更新してから
  // `refresh()` でダッシュボード側のstateに反映する。
  const fetchIssues = useCallback(
    (mode: FetchMode) => {
      const seq = ++requestSeq.current;
      if (mode === "initial") setLoad("loading");
      if (mode === "manual") setRefreshing(true);
      return postRefreshProject(repo)
        .then(async (data) => {
          if (seq !== requestSeq.current) return;
          await refresh();
          if (seq !== requestSeq.current) return;
          storeIssues(repo, data.issues);
          setIssues(data.issues);
          setLoad("ready");
          // 手動再取得の直後に定期更新が重ならないよう、タイマーを仕切り直す。
          if (mode === "manual") restartPoll.current();
        })
        .catch((e) => {
          if (seq !== requestSeq.current) return;
          const message =
            e instanceof Error ? e.message : "issueの取得に失敗しました";
          if (mode === "initial") {
            setErrorMessage(message);
            setLoad("error");
          } else if (mode === "manual") {
            // 表示中の一覧は残したまま通知する。
            showToast(`再取得に失敗しました: ${message}`);
          }
          // 定期更新の失敗では、表示中の一覧を消さずに残す。
        })
        .finally(() => {
          if (seq === requestSeq.current) setRefreshing(false);
        });
    },
    [repo, refresh, showToast, storeIssues],
  );

  useEffect(() => {
    try {
      localStorage.setItem("issueProject", repo);
    } catch {}
    // TTL内のキャッシュは取得せず表示のみ、TTL超過は表示しつつ静かに再取得、無ければ従来通り。
    // 手動再取得（fetchIssues("manual")）は常にキャッシュを無視して取得する。
    const cached = lookupIssues(repo);
    if (cached.kind === "miss") fetchIssues("initial");
    else if (cached.kind === "stale") fetchIssues("poll");
  }, [repo, fetchIssues, lookupIssues]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    const start = () => {
      clearInterval(interval);
      interval = setInterval(
        () => fetchIssues("poll"),
        settings.pollIntervalMs,
      );
    };
    restartPoll.current = start;
    start();
    return () => clearInterval(interval);
  }, [fetchIssues, settings.pollIntervalMs]);

  const ready = load === "ready";
  const orphans = issues.filter((i) => i.is_orphaned);
  const options = buildFilterOptions(issues, showDone);
  const rows = filterIssues(issues, filter, showDone, sort);
  const activeLabel = options.find((o) => o.key === filter)?.label ?? "";
  const doneCount = issues.filter(isClosed).length;
  const hiddenDone =
    filter === FILTER_ALL && !showDone && doneCount > 0
      ? ` · 完了 ${doneCount} 件は非表示`
      : "";
  const doneSwitchLive = filter === FILTER_ALL;

  const statusByRepo = new Map(state.project_status.map((p) => [p.repo, p]));
  const openCountOf = (r: string) => {
    const counts = statusByRepo.get(r)?.counts;
    return counts ? Object.values(counts).reduce((a, b) => a + b, 0) : 0;
  };

  return (
    <div className={styles.page}>
      <div className={styles.projectPanel}>
        <div className={styles.projectHeader}>
          <span className={styles.projectLabel}>プロジェクト</span>
        </div>
        <div className={styles.tabs} role="tablist" aria-label="プロジェクト">
          {repos.map((r) => {
            const selected = r === repo;
            const dot = statusCountMeta(
              statusByRepo.get(r)?.label ?? "status:todo",
            );
            return (
              <div
                key={r}
                className={`${styles.tab} ${selected ? styles.tabSelected : ""}`}
              >
                <Link
                  href={`/projects/${r}`}
                  role="tab"
                  aria-selected={selected}
                  className={styles.tabLink}
                  title={r}
                >
                  <span
                    className={styles.tabDot}
                    style={{ background: `var(${dot.colorVar})` }}
                  />
                  <span className={styles.tabName}>{shortRepoName(r)}</span>
                  {statusByRepo.get(r)?.is_orphaned && (
                    <span
                      className={styles.tabOrphan}
                      title="作業中ラベルですが処理が停止している可能性があります"
                    >
                      <WarningIcon size={12} />
                    </span>
                  )}
                  <span className={styles.tabCount} title="未完了のissue">
                    {openCountOf(r)}
                  </span>
                </Link>
                <button
                  type="button"
                  className={styles.tabIconButton}
                  title="このプロジェクトに新規タスクを作成"
                  aria-label={`${r} に新規タスクを作成`}
                  onClick={() => openNewTask(r)}
                >
                  <PlusIcon size={14} strokeWidth={2.4} />
                </button>
                <a
                  className={styles.tabIconButton}
                  href={`https://github.com/${r}/issues`}
                  target="_blank"
                  rel="noreferrer"
                  title="GitHubで開く"
                  aria-label={`${r} をGitHubで開く`}
                >
                  <ExternalLinkIcon size={13} />
                </a>
              </div>
            );
          })}
        </div>
      </div>

      {ready && orphans.length > 0 && (
        <div className={styles.orphanBanner}>
          <span className={styles.orphanBannerIcon}>
            <WarningIcon size={16} />
          </span>
          <div className={styles.orphanBannerText}>
            <div className={styles.orphanBannerTitle}>
              停止している可能性があるissueが {orphans.length} 件
            </div>
            <div className={styles.orphanBannerBody}>
              「作業中」ラベルのまま、エージェントの処理が一定時間進んでいません。内容を確認し、返信で再開や中止を指示してください。
            </div>
          </div>
          <button
            type="button"
            className={styles.orphanBannerBtn}
            onClick={() =>
              setFilter((f) =>
                f === FILTER_ORPHAN ? FILTER_ALL : FILTER_ORPHAN,
              )
            }
          >
            {filter === FILTER_ORPHAN ? "すべて表示に戻す" : "該当のみ表示"}
          </button>
        </div>
      )}

      <div className={styles.listPanel}>
        <div className={styles.toolbar}>
          <div
            className={styles.filterRow}
            role="group"
            aria-label="状態で絞り込み"
          >
            {options.map((o) => {
              const active = filter === o.key;
              const isOrphan = o.key === FILTER_ORPHAN;
              const dotMeta =
                o.key === FILTER_ALL || isOrphan
                  ? null
                  : statusCountMeta(o.key);
              return (
                <button
                  key={o.key}
                  type="button"
                  aria-pressed={active}
                  className={`${styles.filterBtn} ${active ? styles.filterBtnActive : ""} ${isOrphan ? styles.filterBtnOrphan : ""}`}
                  style={
                    o.count === 0 && !active ? { opacity: 0.55 } : undefined
                  }
                  onClick={() => setFilter(o.key)}
                >
                  {isOrphan && <WarningIcon size={12} />}
                  {dotMeta && (
                    <span
                      className={styles.filterDot}
                      style={{ background: `var(${dotMeta.colorVar})` }}
                    />
                  )}
                  {o.label}
                  <span className={styles.filterCount}>{o.count}</span>
                </button>
              );
            })}
          </div>
          <div className={styles.toolbarRight}>
            <button
              type="button"
              role="switch"
              aria-checked={showDone}
              className={styles.doneSwitch}
              style={{ opacity: doneSwitchLive ? 1 : 0.5 }}
              title={
                doneSwitchLive
                  ? "完了したissueも一覧に含める"
                  : "「すべて」表示時に有効"
              }
              onClick={() => setShowDone((v) => !v)}
            >
              <span
                className={styles.doneTrack}
                style={{
                  background: showDone
                    ? "var(--accent-blue)"
                    : "var(--border-subtle)",
                }}
              >
                <span
                  className={styles.doneKnob}
                  style={{
                    transform: showDone ? "translateX(12px)" : "none",
                  }}
                />
              </span>
              完了を表示
            </button>
            <label className={styles.sortLabel}>
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ flex: "none" }}
                aria-hidden="true"
              >
                <path d="M7 4v16M3 16l4 4 4-4M17 20V4M13 8l4-4 4 4" />
              </svg>
              <select
                className={styles.sortSelect}
                value={sort}
                aria-label="並び替え"
                onChange={(e) => setSort(e.target.value as "desc" | "asc")}
              >
                <option value="desc">更新が新しい順</option>
                <option value="asc">更新が古い順</option>
              </select>
            </label>
            <SyncAgo
              className={styles.sync}
              fetchedAt={statusByRepo.get(repo)?.fetched_at ?? null}
              loadingText={refreshing ? "取得中…" : undefined}
            />
            <RefreshButton
              size="md"
              refreshing={refreshing || load === "loading"}
              title="issueを再取得"
              onClick={() => fetchIssues("manual")}
            />
          </div>
        </div>

        {load === "loading" && (
          <div className={styles.loading}>
            <div className={styles.loadingHead}>
              <svg
                width="15"
                height="15"
                viewBox="0 0 42 42"
                className={styles.spinner}
                aria-hidden="true"
              >
                <circle
                  cx="21"
                  cy="21"
                  r="17"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="5"
                  opacity=".26"
                />
                <circle
                  cx="21"
                  cy="21"
                  r="17"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="5"
                  strokeLinecap="round"
                  strokeDasharray="34 200"
                  className={styles.spinnerArc}
                />
              </svg>
              {repo} のissueを読み込み中…
            </div>
            {SKELETON_WIDTHS.map((w) => (
              <div key={w} className={styles.skeletonRow}>
                <span className={styles.skeletonNum} />
                <span
                  className={styles.skeletonTitle}
                  style={{ width: `${w}%` }}
                />
                <span className={styles.skeletonSpacer} />
                <span className={styles.skeletonBadge} />
                <span className={styles.skeletonTime} />
              </div>
            ))}
          </div>
        )}

        {load === "error" && (
          <div className={styles.empty}>
            <div className={`${styles.emptyIcon} ${styles.emptyIconWarn}`}>
              <svg
                width="26"
                height="26"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.3"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v6M12 16.5v.01" />
              </svg>
            </div>
            <div>
              <div className={styles.emptyTitle}>
                issueを取得できませんでした
              </div>
              <div className={styles.emptyBody}>
                {errorMessage}
                。時間をおいて再試行するか、GitHubで直接確認してください。
              </div>
            </div>
            <div className={styles.emptyActions}>
              <button
                type="button"
                className={styles.primaryBtn}
                onClick={() => fetchIssues("initial")}
              >
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{ flex: "none" }}
                  aria-hidden="true"
                >
                  <path d="M21 12a9 9 0 1 1-2.6-6.4" />
                  <path d="M21 4v5h-5" />
                </svg>
                再試行
              </button>
              <a
                className={styles.ghostBtn}
                href={`https://github.com/${repo}/issues`}
                target="_blank"
                rel="noreferrer"
              >
                GitHubで開く
                <ExternalLinkIcon size={12} />
              </a>
            </div>
          </div>
        )}

        {ready && issues.length === 0 && (
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>
              <svg
                width="26"
                height="26"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.9"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M22 12h-6l-2 3h-4l-2-3H2" />
                <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z" />
              </svg>
            </div>
            <div>
              <div className={styles.emptyTitle}>issueはまだありません</div>
              <div className={styles.emptyBody}>
                {repo} でタスクを作成すると、ここに一覧表示されます。
              </div>
            </div>
            <button
              type="button"
              className={styles.primaryBtn}
              onClick={() => openNewTask(repo)}
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ flex: "none" }}
                aria-hidden="true"
              >
                <path d="M12 5v14M5 12h14" />
              </svg>
              新規タスクを作成
            </button>
          </div>
        )}

        {ready && issues.length > 0 && rows.length === 0 && (
          <div className={`${styles.empty} ${styles.emptyCompact}`}>
            <div className={styles.noMatchTitle}>
              この条件に一致するissueはありません
            </div>
            <div className={styles.noMatchBody}>
              「{activeLabel}」のissueは現在0件です。
            </div>
            <button
              type="button"
              className={styles.ghostBtn}
              onClick={() => setFilter(FILTER_ALL)}
            >
              絞り込みを解除
            </button>
          </div>
        )}

        {ready && rows.length > 0 && (
          <>
            <div className={styles.head}>
              <span>#</span>
              <span>タイトル</span>
              <span>状態</span>
              <span className={styles.headIcon}>
                <CommentIcon size={12} />
              </span>
              <span>更新</span>
              <span />
            </div>
            <div className={styles.rows}>
              {rows.map((issue) => {
                const done = isClosed(issue);
                const url = `https://github.com/${repo}/issues/${issue.number}`;
                const ago = formatRelativeTime(issue.updated_at);
                const absTime = `${formatAbsoluteTime(issue.updated_at)} に更新`;
                const rowClass = [
                  styles.row,
                  done ? styles.rowDone : "",
                  issue.is_orphaned ? styles.rowOrphan : "",
                ].join(" ");
                const cardClass = [
                  styles.card,
                  done ? styles.cardDone : "",
                  issue.is_orphaned ? styles.cardOrphan : "",
                ].join(" ");
                const reply = () => openReply(repo, issue.number, issue.title);
                return (
                  <div key={issue.number} className={styles.item}>
                    <div className={rowClass}>
                      <span className={styles.num}>#{issue.number}</span>
                      <div className={styles.titleCell}>
                        <a
                          className={`${styles.title} ${done ? styles.titleDone : ""}`}
                          href={url}
                          target="_blank"
                          rel="noreferrer"
                          title={issue.title}
                        >
                          {issue.title}
                        </a>
                        {issue.is_orphaned && (
                          <span className={styles.orphanNote}>
                            <WarningIcon size={12} />
                            停止の可能性 · {orphanNote(issue.updated_at)}
                          </span>
                        )}
                      </div>
                      <div className={styles.badgeCell}>
                        <StatusBadge issue={issue} />
                      </div>
                      <span className={styles.num}>{issue.comments_count}</span>
                      <span className={styles.ago} title={absTime}>
                        {ago}
                      </span>
                      <div className={styles.replyCell}>
                        <button
                          type="button"
                          className={styles.replyBtn}
                          onClick={reply}
                        >
                          <ReplyIcon size={13} />
                          返信する
                        </button>
                      </div>
                    </div>
                    <div className={cardClass}>
                      <div className={styles.cardTop}>
                        <StatusBadge issue={issue} />
                        {issue.is_orphaned && (
                          <span className={styles.orphanNoteInline}>
                            <WarningIcon size={12} />
                            停止の可能性
                          </span>
                        )}
                        <span className={styles.cardSpacer} />
                        <span className={styles.num}>#{issue.number}</span>
                      </div>
                      <a
                        className={`${styles.title} ${styles.titleCard} ${done ? styles.titleDone : ""}`}
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {issue.title}
                      </a>
                      <div className={styles.cardMeta}>
                        <span className={styles.metaItem} title={absTime}>
                          <svg
                            width="13"
                            height="13"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2.1"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            style={{ flex: "none" }}
                            aria-hidden="true"
                          >
                            <circle cx="12" cy="12" r="9" />
                            <path d="M12 7v5l3 2" />
                          </svg>
                          {ago}
                        </span>
                        <span className={`${styles.metaItem} ${styles.num}`}>
                          <CommentIcon size={13} />
                          {issue.comments_count}
                        </span>
                        <span className={styles.cardSpacer} />
                        <button
                          type="button"
                          className={styles.replyBtn}
                          onClick={reply}
                        >
                          <ReplyIcon size={14} />
                          返信する
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className={styles.foot}>
              {rows.length} 件を表示{hiddenDone}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
