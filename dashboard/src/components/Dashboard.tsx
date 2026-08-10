"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchProjects, fetchState } from "@/lib/api";
import { deriveProjectStatus } from "@/lib/projectStatus";
import type { AggregatedState } from "@/lib/types";
import Header from "./Header";
import ProjectStatusRow from "./ProjectStatusRow";
import DecisionsList from "./DecisionsList";
import ReviewsList from "./ReviewsList";
import ActivityTimeline from "./ActivityTimeline";
import UsageMonitor from "./UsageMonitor";
import ComposerBar, { type ComposerMode, type IssueRef } from "./ComposerBar";
import Toast from "./Toast";
import styles from "./Dashboard.module.css";

const POLL_INTERVAL_MS = 30_000;
const TOAST_DURATION_MS = 4_600;
const EMPTY_STATE: AggregatedState = {
  decisions: [],
  reviews: [],
  activity: [],
};

export default function Dashboard() {
  const [state, setState] = useState<AggregatedState>(EMPTY_STATE);
  const [repos, setRepos] = useState<string[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [composerOpen, setComposerOpen] = useState(false);
  const [composerMode, setComposerMode] = useState<ComposerMode>("new");
  const [replyTarget, setReplyTarget] = useState<IssueRef | null>(null);
  const [newTaskRepo, setNewTaskRepo] = useState("");

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

  const refresh = useCallback(() => {
    fetchState()
      .then((data) => {
        setState(data);
        setLastUpdated(new Date());
        setError(null);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "状態の取得に失敗しました"),
      );
  }, []);

  useEffect(() => {
    refresh();
    fetchProjects()
      .then((data) => setRepos(data.repos))
      .catch(() => setRepos([]));
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

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
    deriveProjectStatus(repo, state.decisions, state.activity),
  );

  return (
    <div className={styles.page}>
      <Header
        decisionsCount={state.decisions.length}
        projectsCount={repos.length}
        lastUpdated={lastUpdated}
      />
      {error && (
        <div className={styles.banner}>
          {error}（オーケストレータが起動しているか確認してください）
        </div>
      )}
      <ProjectStatusRow
        projects={projectStatuses}
        onQuickCreate={handleQuickCreate}
      />
      <main className={styles.main}>
        <div className={styles.left}>
          <DecisionsList
            decisions={state.decisions}
            onApproved={refresh}
            onReply={handleReply}
            onToast={showToast}
          />
          <ReviewsList
            reviews={state.reviews}
            onApproved={refresh}
            onReply={handleReply}
            onToast={showToast}
          />
        </div>
        <div className={styles.right}>
          <UsageMonitor />
          <ActivityTimeline activity={state.activity} onReply={handleReply} />
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
      />
      <Toast show={toast.show} text={toast.text} />
    </div>
  );
}
