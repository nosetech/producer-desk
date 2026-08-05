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
import ComposerBar, { type ComposerMode, type IssueRef } from "./ComposerBar";
import styles from "./Dashboard.module.css";

const POLL_INTERVAL_MS = 30_000;
const EMPTY_STATE: AggregatedState = { decisions: [], activity: [] };

export default function Dashboard() {
  const [state, setState] = useState<AggregatedState>(EMPTY_STATE);
  const [repos, setRepos] = useState<string[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [composerMode, setComposerMode] = useState<ComposerMode>("reply");
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

  function handleReply(repo: string, issueNumber: number, title: string) {
    setComposerMode("reply");
    setReplyTarget({ repo, number: issueNumber, title });
  }

  function handleQuickCreate(repo: string) {
    setComposerMode("new");
    setNewTaskRepo(repo);
  }

  const projectStatuses = repos.map((repo) =>
    deriveProjectStatus(repo, state.decisions, state.activity),
  );

  const issueRefs: IssueRef[] = [
    ...state.decisions.map((d) => ({
      repo: d.repo,
      number: d.number,
      title: d.title,
    })),
    ...state.activity.map((a) => ({
      repo: a.repo,
      number: a.number,
      title: a.title,
    })),
  ].filter(
    (issue, index, arr) =>
      arr.findIndex(
        (i) => i.repo === issue.repo && i.number === issue.number,
      ) === index,
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
            onReply={handleReply}
            onActed={refresh}
          />
        </div>
        <div className={styles.right}>
          <UsageMonitor />
          <ActivityTimeline activity={state.activity} onReply={handleReply} />
        </div>
      </main>
      <ComposerBar
        mode={composerMode}
        onModeChange={setComposerMode}
        replyTarget={replyTarget}
        onClearReplyTarget={() => setReplyTarget(null)}
        onSelectReplyTarget={setReplyTarget}
        issues={issueRefs}
        repos={repos}
        newTaskRepo={newTaskRepo}
        onNewTaskRepoChange={setNewTaskRepo}
        onSubmitted={refresh}
      />
    </div>
  );
}
