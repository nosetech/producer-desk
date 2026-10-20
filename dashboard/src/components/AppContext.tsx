"use client";

import { createContext, useContext } from "react";
import type {
  AggregatedState,
  IssueComment,
  ProjectExecutionSettings,
} from "@/lib/types";
import type { DashboardSettings } from "@/lib/settings";
import type { IssueCacheLookup } from "@/lib/issueCache";
import type { ProjectIssue } from "@/lib/types";
import type { Job } from "@/lib/jobs";
import type { JobSpec } from "@/lib/useJobs";

export interface AppContextValue {
  state: AggregatedState;
  repos: string[];
  projectSettings: Record<string, ProjectExecutionSettings>;
  error: string | null;
  /** config/projects.yamlのタイミング系設定（issue #201）。取得前・失敗時は従来の固定値。 */
  settings: DashboardSettings;
  /** 実行中・失敗中の操作（承認・マージ・返信・新規作成）。issue単位で独立（issue #212）。 */
  jobs: Job[];
  startJob: (spec: JobSpec) => boolean;
  retryJob: (key: string) => void;
  dismissJob: (key: string) => void;
  refresh: () => Promise<void>;
  refreshProjects: () => Promise<void>;
  /** 指示操作・承認・新規issue作成の成功後に呼ぶ。issue一覧キャッシュを破棄してから`refresh()`する。 */
  refreshAfterAction: () => Promise<void>;
  /** プロジェクト別issue一覧のクライアントキャッシュ（issue #198）。 */
  lookupIssues: (repo: string) => IssueCacheLookup;
  storeIssues: (repo: string, issues: ProjectIssue[]) => void;
  showToast: (text: string, isError?: boolean) => void;
  openReply: (
    repo: string,
    issueNumber: number,
    title: string,
    comment?: IssueComment,
  ) => void;
  openNewTask: (repo: string) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export const AppProvider = AppContext.Provider;

export function useApp(): AppContextValue {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp は AppShell 配下で使用してください");
  return value;
}
