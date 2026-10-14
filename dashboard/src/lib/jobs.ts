import type { StageDef } from "./stageProgress";

export type JobKind = "approve" | "merge" | "reply" | "new";

/**
 * 画面操作（承認・マージ・返信・新規作成）のバックグラウンド実行状態（issue #212）。
 * issue単位（`repo#number`）で保持し、別プロジェクト・別issueの操作を互いに妨げない。
 * 新規作成はissue番号が未確定のため、操作ごとに一意なキーを持つ。
 */
export interface Job {
  key: string;
  kind: JobKind;
  repo: string;
  /** 新規作成ではundefined（作成前はissue番号が無い）。 */
  number?: number;
  title: string;
  stages: StageDef[];
  status: "running" | "error";
  errorMessage?: string;
  /** サーバのon_stageで通知された最新の完了段階（ポーリングで更新）。 */
  polledStage: string | null;
  progressId: string;
}

export function issueKey(repo: string, number: number): string {
  return `${repo}#${number}`;
}

/** 同一issueに対する実行中・失敗中の操作があれば二重操作として拒否する。 */
export function canStartJob(
  jobs: Job[],
  repo: string,
  number: number | undefined,
): boolean {
  if (number === undefined) return true;
  const key = issueKey(repo, number);
  return !jobs.some((j) => j.key === key);
}

export function findIssueJob(
  jobs: Job[],
  repo: string,
  number: number,
): Job | undefined {
  const key = issueKey(repo, number);
  return jobs.find((j) => j.key === key);
}

export function updateJob(
  jobs: Job[],
  key: string,
  patch: Partial<Job>,
): Job[] {
  return jobs.map((j) => (j.key === key ? { ...j, ...patch } : j));
}

export function removeJob(jobs: Job[], key: string): Job[] {
  return jobs.filter((j) => j.key !== key);
}

const FAIL_NOUN: Record<JobKind, string> = {
  approve: "承認",
  merge: "マージ",
  reply: "返信の送信",
  new: "issueの作成",
};

export function jobLabel(job: Pick<Job, "repo" | "number" | "kind">): string {
  const repoName = job.repo.split("/")[1] ?? job.repo;
  return job.number !== undefined
    ? `${repoName} #${job.number}`
    : `${repoName}（新規）`;
}

/** 失敗したissueを特定できる通知文言（例: 「producer-desk #212 の承認に失敗しました。」）。 */
export function failureMessage(job: Pick<Job, "repo" | "number" | "kind">) {
  return `${jobLabel(job)} の${FAIL_NOUN[job.kind]}に失敗しました。`;
}

/** 進行段階（完了済み段階の次）/ 全段階数の表示用。 */
export function progressCount(job: Job, polledIndex: number): string {
  const total = job.stages.length;
  const step = polledIndex + 1 + (job.status === "error" ? 0 : 1);
  return `${Math.min(step, total)} / ${total}`;
}

export function stageIndex(job: Job): number {
  const base = job.polledStage?.replace(/_skipped$/, "") ?? null;
  return base ? job.stages.findIndex((s) => s.key === base) : -1;
}
