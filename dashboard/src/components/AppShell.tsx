"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchProjects, fetchState } from "@/lib/api";
import {
  EMPTY_STATUS_COUNTS,
  type AggregatedState,
  type IssueComment,
  type ProjectExecutionSettings,
} from "@/lib/types";
import { AppProvider } from "./AppContext";
import Header from "./Header";
import Sidebar from "./Sidebar";
import BottomNav from "./BottomNav";
import ComposerBar, { type ComposerMode, type IssueRef } from "./ComposerBar";
import Toast from "./Toast";
import styles from "./AppShell.module.css";

const POLL_INTERVAL_MS = 30_000;
const TOAST_DURATION_MS = 4_600;
const EMPTY_STATE: AggregatedState = {
  decisions: [],
  reviews: [],
  project_status: [],
  status_counts: EMPTY_STATUS_COUNTS,
  last_polled_at: null,
};

/**
 * 全画面共通のレイアウト（ヘッダー・サイドバー／ボトムナビ・指示入力欄・トースト）と、
 * 画面間で共有するポーリング状態を持つ（issue #116）。指示入力欄とトーストは
 * Claude Designに合わせ、サイドバー・ボトムナビを除いたコンテンツ領域に重ねて配置する。
 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AggregatedState>(EMPTY_STATE);
  const [repos, setRepos] = useState<string[]>([]);
  const [projectSettings, setProjectSettings] = useState<
    Record<string, ProjectExecutionSettings>
  >({});
  const [error, setError] = useState<string | null>(null);

  const [composerOpen, setComposerOpen] = useState(false);
  const [composerMode, setComposerMode] = useState<ComposerMode>("new");
  const [replyTarget, setReplyTarget] = useState<IssueRef | null>(null);
  const [newTaskRepo, setNewTaskRepo] = useState("");
  const [lockedIssue, setLockedIssue] = useState<IssueRef | null>(null);

  const [toast, setToast] = useState<{ show: boolean; text: string }>({
    show: false,
    text: "",
  });
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((text: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ show: true, text });
    toastTimer.current = setTimeout(
      () => setToast((t) => ({ ...t, show: false })),
      TOAST_DURATION_MS,
    );
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  const refresh = useCallback((): Promise<void> => {
    return fetchState()
      .then((data) => {
        setState(data);
        setError(null);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "状態の取得に失敗しました");
      });
  }, []);

  const refreshProjects = useCallback((): Promise<void> => {
    // refresh()と同様、取得失敗時は前回の一覧を残す（別タブでのプロジェクト設定変更や
    // config/projects.yaml直接編集を定期反映するためのポーリング対象でもあるため、
    // 一時的な取得失敗でプロジェクト一覧・PROXY表示を消さない）。
    return fetchProjects()
      .then((data) => {
        setRepos(data.repos);
        setProjectSettings(data.settings);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    refreshProjects();
    const interval = setInterval(() => {
      refresh();
      refreshProjects();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [refresh, refreshProjects]);

  const openReply = useCallback(
    (
      repo: string,
      issueNumber: number,
      title: string,
      comment?: IssueComment,
    ) => {
      setComposerMode("reply");
      // 返信先コメントは返信を開いた時点のスナップショットを保持する（ポーリングで
      // commentsが更新されても入れ替えない）。
      setReplyTarget({
        repo,
        number: issueNumber,
        title,
        comment,
        openedAt: new Date().toISOString(),
      });
      setComposerOpen(true);
    },
    [],
  );

  const openNewTask = useCallback((repo: string) => {
    setComposerMode("new");
    setNewTaskRepo(repo);
    setComposerOpen(true);
  }, []);

  const attentionCount = state.decisions.length + state.reviews.length;
  const anyOrphan = state.project_status.some((p) => p.is_orphaned);

  return (
    <AppProvider
      value={{
        state,
        repos,
        projectSettings,
        error,
        lockedIssue,
        refresh,
        refreshProjects,
        showToast,
        openReply,
        openNewTask,
      }}
    >
      <div className={styles.shell}>
        <Header />
        <div className={styles.body}>
          <Sidebar attentionCount={attentionCount} anyOrphan={anyOrphan} />
          <div className={styles.contentPane}>
            <div className={styles.screen}>{children}</div>
            <Toast show={toast.show} text={toast.text} />
            <ComposerBar
              open={composerOpen}
              mode={composerMode}
              replyTarget={replyTarget}
              onClearReplyTarget={() => setReplyTarget(null)}
              onOpen={() => {
                setComposerMode("new");
                setComposerOpen(true);
              }}
              onClose={() => setComposerOpen(false)}
              repos={repos}
              newTaskRepo={newTaskRepo}
              onNewTaskRepoChange={setNewTaskRepo}
              onSubmitted={refresh}
              onReplySubmittingChange={setLockedIssue}
            />
          </div>
          <BottomNav attentionCount={attentionCount} anyOrphan={anyOrphan} />
        </div>
      </div>
    </AppProvider>
  );
}
