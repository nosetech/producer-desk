import {
  EMPTY_STATUS_COUNTS,
  type AggregatedState,
  type CreateIssueResult,
  type Dispatch,
  type ExecutionMode,
  type InstructAction,
  type InstructResult,
  type ProgressResponse,
  type ProjectIssuesResponse,
  type ProjectSettingsResponse,
  type ProjectsResponse,
  type UpdateProjectSettingsResult,
  type UsageResponse,
} from "./types";
import {
  DEFAULT_DASHBOARD_SETTINGS,
  parseDashboardSettings,
  type DashboardSettings,
} from "./settings";

async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  const data = await res.json();
  if (!res.ok) {
    const message =
      typeof data?.error === "string" ? data.error : `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data as T;
}

export function fetchState(): Promise<AggregatedState> {
  return fetch("/api/state", { cache: "no-store" })
    .then((res) => parseJsonOrThrow<AggregatedState>(res))
    .then((data) => ({
      // orchestrator・dashboardは別プロセスとして個別に再起動されるため、
      // dashboardの再起動後もorchestratorがまだ旧コードのままの期間は
      // レスポンスに新フィールドが含まれないことがある（issue #58デプロイ後に発生）。
      // 欠けているフィールドは空配列にフォールバックし、両プロセスの
      // 再起動タイミングがずれても画面がクラッシュしないようにする。
      decisions: data.decisions ?? [],
      reviews: data.reviews ?? [],
      project_status: (data.project_status ?? []).map((p) => ({
        ...p,
        fetched_at: p.fetched_at ?? null,
      })),
      status_counts: data.status_counts ?? EMPTY_STATUS_COUNTS,
      last_polled_at: data.last_polled_at ?? null,
    }));
}

export function fetchProjects(): Promise<ProjectsResponse> {
  return fetch("/api/projects", { cache: "no-store" })
    .then((res) => parseJsonOrThrow<ProjectsResponse>(res))
    .then((data) => ({
      repos: data.repos ?? [],
      settings: data.settings ?? {},
    }));
}

export function fetchUsage(): Promise<UsageResponse> {
  return fetch("/api/usage", { cache: "no-store" }).then((res) =>
    parseJsonOrThrow<UsageResponse>(res),
  );
}

/** 取得失敗・不正値は従来の固定値にフォールバックする（issue #201）。 */
export function fetchSettings(): Promise<DashboardSettings> {
  return fetch("/api/settings", { cache: "no-store" })
    .then((res) => parseJsonOrThrow<unknown>(res))
    .then(parseDashboardSettings)
    .catch(() => DEFAULT_DASHBOARD_SETTINGS);
}

function repoPath(repo: string): string {
  const [owner, name] = repo.split("/");
  return `/api/projects/${owner}/${name}`;
}

export function postInstruct(
  repo: string,
  issueNumber: number,
  action: InstructAction,
  message?: string,
  progressId?: string,
): Promise<InstructResult> {
  return fetch(`${repoPath(repo)}/issues/${issueNumber}/instruct`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, message, progressId }),
  }).then((res) => parseJsonOrThrow<InstructResult>(res));
}

export function postCreateIssue(
  repo: string,
  title: string,
  prompt: string,
  dispatch: Dispatch,
  progressId?: string,
): Promise<CreateIssueResult> {
  return fetch(`${repoPath(repo)}/issues`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, prompt, dispatch, progressId }),
  }).then((res) => parseJsonOrThrow<CreateIssueResult>(res));
}

export function fetchProjectSettings(
  repo: string,
): Promise<ProjectSettingsResponse> {
  return fetch(`${repoPath(repo)}/settings`, { cache: "no-store" }).then(
    (res) => parseJsonOrThrow<ProjectSettingsResponse>(res),
  );
}

export function patchProjectSettings(
  repo: string,
  executionMode: ExecutionMode,
  litellmModel: string | null,
): Promise<UpdateProjectSettingsResult> {
  return fetch(`${repoPath(repo)}/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      execution_mode: executionMode,
      litellm_model: litellmModel,
    }),
  }).then((res) => parseJsonOrThrow<UpdateProjectSettingsResult>(res));
}

// 指示送信中の実際の進捗（orchestrator/orchestrator/server.py の ProgressStore）を
// 取得する。ComposerBarが送信中に短間隔でポーリングし、擬似進行ではなく実際に
// 完了したステップを表示するために使う。
export function fetchProgress(progressId: string): Promise<ProgressResponse> {
  return fetch(`/api/progress/${progressId}`, { cache: "no-store" }).then(
    (res) => parseJsonOrThrow<ProgressResponse>(res),
  );
}

export function fetchProjectIssues(
  repo: string,
): Promise<ProjectIssuesResponse> {
  return fetch(`${repoPath(repo)}/issues`, { cache: "no-store" }).then((res) =>
    parseJsonOrThrow<ProjectIssuesResponse>(res),
  );
}

/**
 * 1プロジェクト分のissue・ラベル情報をGitHubから再取得する（issue #197）。
 * オーケストレータのStateStoreも当該リポジトリ分のみ更新されるため、呼び出し後に
 * `useApp().refresh()` でラベル別件数・更新時刻を反映する。
 */
export function postRefreshProject(
  repo: string,
): Promise<ProjectIssuesResponse> {
  return fetch(`${repoPath(repo)}/refresh`, {
    method: "POST",
    cache: "no-store",
  }).then((res) => parseJsonOrThrow<ProjectIssuesResponse>(res));
}

/** 全プロジェクトの情報をGitHubから再取得する（issue #197）。 */
export function postRefreshAll(): Promise<void> {
  return fetch("/api/refresh", { method: "POST", cache: "no-store" }).then(
    (res) => parseJsonOrThrow<unknown>(res).then(() => undefined),
  );
}
