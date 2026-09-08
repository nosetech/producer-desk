"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchProjects, fetchState } from "@/lib/api";
import { deriveProjectStatus } from "@/lib/projectStatus";
import {
  EMPTY_STATUS_COUNTS,
  type AggregatedState,
  type ProjectExecutionSettings,
} from "@/lib/types";
import Header from "./Header";
import ProjectStatusRow from "./ProjectStatusRow";
import ProjectSettingsDialog from "./ProjectSettingsDialog";
import DecisionsList from "./DecisionsList";
import ReviewsList from "./ReviewsList";
import UsageMonitor from "./UsageMonitor";
import ComposerBar, { type ComposerMode, type IssueRef } from "./ComposerBar";
import Toast from "./Toast";
import styles from "./Dashboard.module.css";

const POLL_INTERVAL_MS = 30_000;
const TOAST_DURATION_MS = 4_600;
const EMPTY_STATE: AggregatedState = {
  decisions: [],
  reviews: [],
  project_status: [],
  status_counts: EMPTY_STATUS_COUNTS,
};

export default function Dashboard() {
  const [state, setState] = useState<AggregatedState>(EMPTY_STATE);
  const [repos, setRepos] = useState<string[]>([]);
  const [projectSettings, setProjectSettings] = useState<
    Record<string, ProjectExecutionSettings>
  >({});
  const [settingsRepo, setSettingsRepo] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
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
        setLastUpdated(new Date());
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

  function handleReply(repo: string, issueNumber: number, title: string) {
    setComposerMode("reply");
    setReplyTarget({ repo, number: issueNumber, title });
    setComposerOpen(true);
  }

  function handleQuickCreate(repo: string) {
    setComposerMode("new");
    setNewTaskRepo(repo);
    setComposerOpen(true);
  }

  function handleOpenComposer() {
    setComposerMode("new");
    setComposerOpen(true);
  }

  const projectStatuses = repos.map((repo) =>
    deriveProjectStatus(
      repo,
      state.decisions,
      state.project_status,
      projectSettings[repo],
    ),
  );

  return (
    <div className={styles.page}>
      <Header lastUpdated={lastUpdated} />
      {error && (
        <div className={styles.banner}>
          {error}（オーケストレータが起動しているか確認してください）
        </div>
      )}
      <ProjectStatusRow
        projects={projectStatuses}
        onQuickCreate={handleQuickCreate}
        onOpenSettings={setSettingsRepo}
      />
      <main className={styles.main}>
        <div className={styles.left}>
          <DecisionsList
            decisions={state.decisions}
            onApproved={refresh}
            onReply={handleReply}
            onToast={showToast}
            lockedIssue={lockedIssue}
          />
          <ReviewsList
            reviews={state.reviews}
            onApproved={refresh}
            onReply={handleReply}
            onToast={showToast}
            lockedIssue={lockedIssue}
          />
        </div>
        <div className={styles.right}>
          <UsageMonitor />
        </div>
      </main>
      <ComposerBar
        open={composerOpen}
        mode={composerMode}
        replyTarget={replyTarget}
        onClearReplyTarget={() => setReplyTarget(null)}
        onOpen={handleOpenComposer}
        onClose={() => setComposerOpen(false)}
        repos={repos}
        newTaskRepo={newTaskRepo}
        onNewTaskRepoChange={setNewTaskRepo}
        onSubmitted={refresh}
        onReplySubmittingChange={setLockedIssue}
      />
      <Toast show={toast.show} text={toast.text} />
      {settingsRepo && (
        <ProjectSettingsDialog
          repo={settingsRepo}
          onClose={() => setSettingsRepo(null)}
          onSaved={refreshProjects}
          onToast={showToast}
        />
      )}
    </div>
  );
}
