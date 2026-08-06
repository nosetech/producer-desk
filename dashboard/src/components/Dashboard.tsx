"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchProjects, fetchState } from "@/lib/api";
import { deriveProjectStatus } from "@/lib/projectStatus";
import type { AggregatedState } from "@/lib/types";
import Header from "./Header";
import ProjectStatusRow from "./ProjectStatusRow";
import DecisionsList from "./DecisionsList";
import ActivityTimeline from "./ActivityTimeline";
import UsageMonitor from "./UsageMonitor";
import ComposerBar, {
  type ComposerMode,
  type IssueRef,
  type ReplyKind,
} from "./ComposerBar";
import styles from "./Dashboard.module.css";

const POLL_INTERVAL_MS = 30_000;
const EMPTY_STATE: AggregatedState = { decisions: [], activity: [] };

export default function Dashboard() {
  const [state, setState] = useState<AggregatedState>(EMPTY_STATE);
  const [repos, setRepos] = useState<string[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [composerOpen, setComposerOpen] = useState(false);
  const [composerMode, setComposerMode] = useState<ComposerMode>("new");
  const [replyKind, setReplyKind] = useState<ReplyKind>("reply");
  const [replyTarget, setReplyTarget] = useState<IssueRef | null>(null);
  const [newTaskRepo, setNewTaskRepo] = useState("");

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

  function openComposerFor(
    repo: string,
    issueNumber: number,
    title: string,
    kind: ReplyKind,
  ) {
    setComposerMode("reply");
    setReplyKind(kind);
    setReplyTarget({ repo, number: issueNumber, title });
    setComposerOpen(true);
  }

  function handleReply(repo: string, issueNumber: number, title: string) {
    openComposerFor(repo, issueNumber, title, "reply");
  }

  function handleApprove(repo: string, issueNumber: number, title: string) {
    openComposerFor(repo, issueNumber, title, "approve");
  }

  function handleReject(repo: string, issueNumber: number, title: string) {
    openComposerFor(repo, issueNumber, title, "reject");
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
            onApprove={handleApprove}
            onReject={handleReject}
            onReply={handleReply}
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
        replyKind={replyKind}
        onClearReplyTarget={() => setReplyTarget(null)}
        onOpen={handleOpenComposer}
        onClose={() => setComposerOpen(false)}
        repos={repos}
        newTaskRepo={newTaskRepo}
        onNewTaskRepoChange={setNewTaskRepo}
        onSubmitted={refresh}
      />
    </div>
  );
}
