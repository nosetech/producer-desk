import {
  EMPTY_STATUS_COUNTS,
  type AggregatedState,
  type CreateIssueResult,
  type DispatchStatus,
  type Dispatch,
  type ExecutionMode,
  type InstructAction,
  type InstructResult,
  type IssueDetail,
  type PrCandidate,
  type ProgressResponse,
  type ProjectIssuesResponse,
  type ProjectSettingsResponse,
  type ProjectsResponse,
  type UpdateProjectSettingsResult,
  type UsageResponse,
} from "./types";
import type { PlanErrorKind } from "./planFlow";
import {
  DEFAULT_DASHBOARD_SETTINGS,
  parseDashboardSettings,
  type DashboardSettings,
} from "./settings";

/**
 * 承認時に対応PRを一意に特定できなかった場合のエラー（409 `pr_selection_required`、
 * issue #206）。ポーリング後に候補が変わった場合等に、返された最新の候補で
 * PR選択UIを開くために使う。
 */
export class PrSelectionRequiredError extends Error {
  readonly candidates: PrCandidate[];

  constructor(message: string, candidates: PrCandidate[]) {
    super(message);
    this.name = "PrSelectionRequiredError";
    this.candidates = candidates;
  }
}

async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  const data = await res.json();
  if (!res.ok) {
    const message =
      typeof data?.error === "string" ? data.error : `HTTP ${res.status}`;
    if (res.status === 409 && data?.code === "pr_selection_required") {
      throw new PrSelectionRequiredError(
        message,
        Array.isArray(data.pr_candidates) ? data.pr_candidates : [],
      );
    }
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
      reviews: (data.reviews ?? []).map((r) => ({
        ...r,
        pr_candidates: r.pr_candidates ?? [],
      })),
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
  prNumber?: number,
): Promise<InstructResult> {
  return fetch(`${repoPath(repo)}/issues/${issueNumber}/instruct`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, message, progressId, prNumber }),
  }).then((res) => parseJsonOrThrow<InstructResult>(res));
}

/** 指示の処理状態を診断する（issue #215）。 */
export function fetchDispatchStatus(
  repo: string,
  issueNumber: number,
): Promise<DispatchStatus> {
  return fetch(`${repoPath(repo)}/issues/${issueNumber}/dispatch-status`, {
    cache: "no-store",
  }).then((res) => parseJsonOrThrow<DispatchStatus>(res));
}

/** 未処理の指示をコメント再投稿なしで再実行する（issue #215）。 */
export function postRedispatch(
  repo: string,
  issueNumber: number,
  progressId?: string,
): Promise<{ dispatched: boolean; comment: string | null }> {
  return fetch(`${repoPath(repo)}/issues/${issueNumber}/redispatch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ progressId }),
  }).then((res) =>
    parseJsonOrThrow<{ dispatched: boolean; comment: string | null }>(res),
  );
}

/**
 * 判断待ちのissueをレビュー待ち（status:in-review）へ変更する（issue #274）。
 * ラベル変更のみで、AIへの指示コメントは投稿されない。
 */
export function postMarkInReview(
  repo: string,
  issueNumber: number,
  progressId?: string,
): Promise<{ label: string }> {
  return fetch(`${repoPath(repo)}/issues/${issueNumber}/mark-in-review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ progressId }),
  }).then((res) => parseJsonOrThrow<{ label: string }>(res));
}

/** 計画生成APIのエラー。`kind`でダッシュボードのエラー表示を切り替える。 */
export class PlanApiError extends Error {
  readonly kind: PlanErrorKind;

  constructor(message: string, kind: PlanErrorKind) {
    super(message);
    this.name = "PlanApiError";
    this.kind = kind;
  }
}

/**
 * やりたいことからissueの計画（タイトル・本文）をAIに作成させる（issue #287）。
 * issueは作成しない。承認後の登録は`postCreateIssue`を使う。
 */
export async function postIssuePlan(
  repo: string,
  input: {
    request: string;
    previousPlan?: { title: string; body: string };
    instruction?: string;
    /** モデル選択値（`claude_code` / `litellm:<alias>`）。省略時はプロジェクトの既定。 */
    model?: string;
  },
  progressId?: string,
): Promise<{ title: string; body: string }> {
  const res = await fetch(`${repoPath(repo)}/issue-plans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...input, progressId }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const code = data?.code;
    const kind: PlanErrorKind =
      code === "parse" || code === "timeout" || code === "limit"
        ? code
        : "failed";
    throw new PlanApiError(
      typeof data?.error === "string" ? data.error : `HTTP ${res.status}`,
      kind,
    );
  }
  return data as { title: string; body: string };
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

/** 単一issueの本文とコメントを取得する（issue #231）。 */
export function fetchIssueDetail(
  repo: string,
  issueNumber: number,
): Promise<IssueDetail> {
  return fetch(`${repoPath(repo)}/issues/${issueNumber}`, {
    cache: "no-store",
  }).then((res) => parseJsonOrThrow<IssueDetail>(res));
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
