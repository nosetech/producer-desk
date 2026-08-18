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
  /** `status:in-review` のissueについてのみ、紐づくPR番号が入る（issue #58）。 */
  pr_number: number | null;
}

/** GET /api/state の activity 配列要素。オーケストレータのActivityEventに対応。 */
export interface ActivityEvent {
  repo: string;
  number: number;
  title: string;
  label: StatusLabel;
  updated_at: string;
  /** `status:in-progress`なのに対応するAgent Runnerが実行中でない孤立状態か（issue #50）。 */
  is_orphaned: boolean;
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

export interface AggregatedState {
  decisions: IssueSummary[];
  reviews: IssueSummary[];
  activity: ActivityEvent[];
  status_counts: StatusCounts;
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
}

export type InstructAction = "approve" | "instruct";

export interface InstructResult {
  action: InstructAction;
  comment: string;
  label: string | null;
  dispatched: boolean;
}

export type Dispatch = "immediate" | "queued";

export interface CreateIssueResult {
  issue_number: number;
  dispatched: boolean;
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
