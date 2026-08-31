import {
  EMPTY_STATUS_COUNTS,
  type AggregatedState,
  type CreateIssueResult,
  type Dispatch,
  type InstructAction,
  type InstructResult,
  type ProgressResponse,
  type ProjectsResponse,
  type UsageResponse,
} from "./types";

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
      project_status: data.project_status ?? [],
      status_counts: data.status_counts ?? EMPTY_STATUS_COUNTS,
    }));
}

export function fetchProjects(): Promise<ProjectsResponse> {
  return fetch("/api/projects", { cache: "no-store" }).then((res) =>
    parseJsonOrThrow<ProjectsResponse>(res),
  );
}

export function fetchUsage(): Promise<UsageResponse> {
  return fetch("/api/usage", { cache: "no-store" }).then((res) =>
    parseJsonOrThrow<UsageResponse>(res),
  );
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

// 指示送信中の実際の進捗（orchestrator/orchestrator/server.py の ProgressStore）を
// 取得する。ComposerBarが送信中に短間隔でポーリングし、擬似進行ではなく実際に
// 完了したステップを表示するために使う。
export function fetchProgress(progressId: string): Promise<ProgressResponse> {
  return fetch(`/api/progress/${progressId}`, { cache: "no-store" }).then(
    (res) => parseJsonOrThrow<ProgressResponse>(res),
  );
}
