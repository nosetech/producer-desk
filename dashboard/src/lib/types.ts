import type { StatusLabel } from "./status";

/** `gh issue list --json comments` の1要素。 */
export interface IssueComment {
  body: string;
  createdAt: string;
  author?: { login: string };
}

/** GET /api/state の decisions 配列要素。オーケストレータのIssueSummaryに対応。 */
export interface IssueSummary {
  repo: string;
  number: number;
  title: string;
  labels: string[];
  comments: IssueComment[];
  updated_at: string;
}

/** GET /api/state の activity 配列要素。オーケストレータのActivityEventに対応。 */
export interface ActivityEvent {
  repo: string;
  number: number;
  title: string;
  label: StatusLabel;
  updated_at: string;
}

export interface AggregatedState {
  decisions: IssueSummary[];
  activity: ActivityEvent[];
}

export interface ProjectsResponse {
  repos: string[];
}

export type InstructAction = "approve" | "reject" | "instruct";

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
