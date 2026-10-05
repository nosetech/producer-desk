"use client";

import { createContext, useContext } from "react";
import type {
  AggregatedState,
  IssueComment,
  ProjectExecutionSettings,
} from "@/lib/types";
import type { IssueRef } from "./ComposerBar";

export interface AppContextValue {
  state: AggregatedState;
  repos: string[];
  projectSettings: Record<string, ProjectExecutionSettings>;
  error: string | null;
  lockedIssue: IssueRef | null;
  refresh: () => Promise<void>;
  refreshProjects: () => Promise<void>;
  showToast: (text: string) => void;
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
