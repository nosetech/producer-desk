"use client";

import { useState } from "react";
import { postRefreshAll } from "@/lib/api";
import { deriveProjectStatus } from "@/lib/projectStatus";
import { useApp } from "./AppContext";
import ProjectStatusRow from "./ProjectStatusRow";
import ProjectSettingsDialog from "./ProjectSettingsDialog";
import DecisionsList from "./DecisionsList";
import ReviewsList from "./ReviewsList";
import UsageMonitor from "./UsageMonitor";
import styles from "./Dashboard.module.css";

export default function Dashboard() {
  const {
    state,
    repos,
    projectSettings,
    error,
    lockedIssue,
    refresh,
    refreshAfterAction,
    refreshProjects,
    showToast,
    openReply,
    openNewTask,
  } = useApp();
  const [settingsRepo, setSettingsRepo] = useState<string | null>(null);
  const [refreshingAll, setRefreshingAll] = useState(false);

  // 全プロジェクトのissue・ラベル情報をGitHubから再取得する（issue #197）。
  // 失敗時は表示中の内容を残したままToastで通知する。
  const refreshAll = () => {
    if (refreshingAll) return;
    setRefreshingAll(true);
    postRefreshAll()
      .then(() => refresh())
      .catch((e) =>
        showToast(
          e instanceof Error
            ? `再取得に失敗しました: ${e.message}`
            : "再取得に失敗しました",
        ),
      )
      .finally(() => setRefreshingAll(false));
  };

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
      {error && (
        <div className={styles.banner}>
          {error}（オーケストレータが起動しているか確認してください）
        </div>
      )}
      <ProjectStatusRow
        projects={projectStatuses}
        onQuickCreate={openNewTask}
        onOpenSettings={setSettingsRepo}
        refreshing={refreshingAll}
        onRefreshAll={refreshAll}
      />
      <main className={styles.main}>
        <div className={styles.left}>
          <DecisionsList
            decisions={state.decisions}
            onApproved={refreshAfterAction}
            onReply={openReply}
            onToast={showToast}
            lockedIssue={lockedIssue}
          />
          <ReviewsList
            reviews={state.reviews}
            onApproved={refreshAfterAction}
            onReply={openReply}
            onToast={showToast}
            lockedIssue={lockedIssue}
          />
        </div>
        <div className={styles.right}>
          <UsageMonitor />
        </div>
      </main>
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
