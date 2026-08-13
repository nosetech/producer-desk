import type { StatusLabel } from "./status";

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

export interface AggregatedState {
  decisions: IssueSummary[];
  reviews: IssueSummary[];
  activity: ActivityEvent[];
}

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
