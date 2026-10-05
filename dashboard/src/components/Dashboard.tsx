"use client";

import { useState } from "react";
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
    refreshProjects,
    showToast,
    openReply,
    openNewTask,
  } = useApp();
  const [settingsRepo, setSettingsRepo] = useState<string | null>(null);

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
      />
      <main className={styles.main}>
        <div className={styles.left}>
          <DecisionsList
            decisions={state.decisions}
            onApproved={refresh}
            onReply={openReply}
            onToast={showToast}
            lockedIssue={lockedIssue}
          />
          <ReviewsList
            reviews={state.reviews}
            onApproved={refresh}
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
