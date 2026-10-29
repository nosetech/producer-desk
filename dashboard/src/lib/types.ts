import {
  STATUS_IN_PROGRESS,
  STATUS_IN_REVIEW,
  STATUS_NEEDS_HUMAN_DECISION,
  STATUS_TODO,
  type StatusLabel,
} from "./status";

/** `gh issue list --json comments` の1要素。 */
export interface IssueComment {
  body: string;
  createdAt: string;
  author?: { login: string };
  url: string;
}

/** GET /api/state の decisions/reviews 配列要素。オーケストレータのIssueSummaryに対応。 */
export interface IssueSummary {
  repo: string;
  number: number;
  title: string;
  labels: string[];
  comments: IssueComment[];
  updated_at: string;
  /**
   * `status:in-review` のissueについてのみ、対応PRを一意に特定できた場合のPR番号が入る
   * （issue #58）。候補が0件または2件以上の場合はnull（issue #206）。
   */
  pr_number: number | null;
  /** `status:in-review` のissueの対応PR候補（issue #206）。 */
  pr_candidates: PrCandidate[];
}

/** issueの対応PR候補。オーケストレータのPrCandidateに対応する（issue #206）。 */
export interface PrCandidate {
  number: number;
  title: string;
  url: string;
  is_draft: boolean;
  head_ref_name: string;
  base_ref_name: string;
}

/**
 * GET /api/state の status_counts。オーケストレータのstatus_counts（`aggregate()`、
 * issue #115）に対応する、状態別のOPEN issue件数。`untagged`は5つの状態ラベルの
 * いずれも付与されていないissue（ラベル付け漏れの検知用途）で、`StatusLabel`の
 * 値域には含まれない。`status:closed`は含まない。
 */
export interface StatusCounts {
  [STATUS_TODO]: number;
  [STATUS_IN_PROGRESS]: number;
  [STATUS_NEEDS_HUMAN_DECISION]: number;
  [STATUS_IN_REVIEW]: number;
  untagged: number;
}

/** ディスパッチキュー上の1エントリ（issue #233）。issueが一覧に無ければtitle・labelともnull。 */
export interface QueueEntry {
  number: number;
  title: string | null;
  label: StatusLabel | null;
}

/** プロジェクトのディスパッチキュー状態（実行中1件＋待機中、待機はFIFO順）。 */
export interface ProjectQueue {
  running: QueueEntry | null;
  waiting: QueueEntry[];
}

/**
 * GET /api/state の project_status 配列要素。オーケストレータのProjectStatus
 * （`aggregate()`）に対応する、プロジェクト（リポジトリ）単位の「並行状況」ウィジェット
 * 向け集計。かつての横断タイムライン（`activity`）はissue #121で廃止され、この
 * フィールドに一本化された。
 */
export interface ProjectStatusSummary {
  repo: string;
  /** 直近更新issueの状態ラベル。管理対象issueが1件も無いリポジトリはnull。 */
  label: StatusLabel | null;
  number: number | null;
  title: string | null;
  /** `status:in-progress`なのに対応するAgent Runnerが実行中でない孤立状態か（issue #50）。 */
  is_orphaned: boolean;
  /** そのリポジトリ単体の状態別OPEN issue件数（`status:closed`は含まない）。 */
  counts: StatusCounts;
  /** オーケストレータが実際にGitHubからこのリポジトリを取得した時刻（ISO 8601、issue #197）。 */
  fetched_at: string | null;
  /** リクエスト時点のディスパッチキュー状態（issue #233）。 */
  queue: ProjectQueue;
}

export interface AggregatedState {
  decisions: IssueSummary[];
  reviews: IssueSummary[];
  project_status: ProjectStatusSummary[];
  status_counts: StatusCounts;
  /** オーケストレータの最終ポーリング時刻（ISO 8601、issue #197）。未ポーリングならnull。 */
  last_polled_at: string | null;
}

export const EMPTY_STATUS_COUNTS: StatusCounts = {
  [STATUS_TODO]: 0,
  [STATUS_IN_PROGRESS]: 0,
  [STATUS_NEEDS_HUMAN_DECISION]: 0,
  [STATUS_IN_REVIEW]: 0,
  untagged: 0,
};

export interface ProjectsResponse {
  repos: string[];
  settings: Record<string, ProjectExecutionSettings>;
}

// 自走タスク本体の実行手段（issue #148・#174・#176、basic-design.md 4章）。
export type ExecutionMode = "claude_code" | "litellm_proxy";

export interface ProjectExecutionSettings {
  execution_mode: ExecutionMode;
  litellm_model: string | null;
}

/** GET /api/projects/{owner}/{name}/settings のレスポンス。 */
export interface ProjectSettingsResponse extends ProjectExecutionSettings {
  repo: string;
  /** `config/litellm_config.yaml`の`model_list`のうち当該repo向けに定義済みのモデルエイリアス。 */
  available_models: string[];
}

/** PATCH /api/projects/{owner}/{name}/settings（オーケストレータへプロキシ）のレスポンス。 */
export interface UpdateProjectSettingsResult extends ProjectExecutionSettings {
  repo: string;
}

export type InstructAction = "approve" | "instruct";

export interface InstructResult {
  action: InstructAction;
  comment: string;
  label: string | null;
  dispatched: boolean;
}

/** GET .../issues/{n}/dispatch-status のレスポンス（issue #215）。 */
export type DispatchState =
  | "running"
  | "queued"
  | "completed"
  | "not_dispatched"
  | "orphaned_in_progress"
  | "not_managed";

export interface DispatchStatus {
  state: DispatchState;
  label: string | null;
  redispatchable: boolean;
  pending_message: string | null;
  pending_comment_id: string | null;
  pending_comment_author: string | null;
  pending_comment_created_at: string | null;
  pending_comment_url: string | null;
  detail: string;
}

export type Dispatch = "immediate" | "queued";

export interface CreateIssueResult {
  issue_number: number;
  dispatched: boolean;
}

// instruct/create_issueの処理中にサーバ側（orchestrator/orchestrator/instruct.py の
// on_stageコールバック）が実際に完了したステップを返す（"comment"/"label"/"issue"/
// "dispatch"）。処理が見つからない・未開始の場合はnull。
export interface ProgressResponse {
  stage: string | null;
}

/** GET /api/usage の daily 配列要素。オーケストレータのDailyModelUsageに対応。 */
export interface DailyUsage {
  date: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_cost_usd: number;
}

/** GET /api/usage の currentLimit。オーケストレータのLimitStatusに対応。 */
export interface CurrentLimitStatus {
  repo: string;
  issue_number: number;
  recorded_at: string;
  api_error_status: number | null;
  error_message: string;
  reset_at_text: string | null;
}

export interface UsageResponse {
  daily: DailyUsage[];
  currentLimit: CurrentLimitStatus | null;
}

/** GET /api/projects/{owner}/{name}/issues の issues 配列要素（issue #116）。 */
export interface ProjectIssue {
  number: number;
  title: string;
  /** 表示に採用する状態ラベル。タグなし（OPENで状態ラベル無し）はnull。 */
  label: StatusLabel | null;
  state: string;
  comments_count: number;
  updated_at: string;
  /** `status:in-progress`なのに対応するAgent Runnerが実行中でない孤立状態か（issue #50）。 */
  is_orphaned: boolean;
}

/** GET /api/projects/{repo}/issues/{n} の応答（issue #231）。返信UIの引用表示用。 */
export interface IssueDetail {
  repo: string;
  number: number;
  body: string;
  author: { login: string } | null;
  created_at: string | null;
  url: string | null;
  comments: IssueComment[];
}

export interface ProjectIssuesResponse {
  repo: string;
  issues: ProjectIssue[];
}

/** GET /api/prompts の prompts 配列要素（issue #149）。 */
export interface PromptInfo {
  key: string;
  title: string;
  description: string;
  /** 現在の本文（上書きがあれば上書き、無ければデフォルト）。 */
  text: string;
  default: string;
  is_default: boolean;
  required_tokens: { token: string; reason: string }[];
  /** 本文中で使えるプレースホルダ名（波括弧なし）。 */
  placeholders: string[];
  /** falseの項目（ユーザーの呼称等）は改行・波括弧を含められない短い語句。 */
  multiline: boolean;
}
