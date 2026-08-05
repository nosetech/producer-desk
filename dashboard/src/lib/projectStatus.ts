import { STATUS_TODO, type StatusLabel } from "./status";
import type { ActivityEvent, IssueSummary } from "./types";

export interface ProjectStatus {
  repo: string;
  label: StatusLabel;
  subtitle: string;
  decisionCount: number;
}

function shortRepoName(repo: string): string {
  return repo.split("/")[1] ?? repo;
}

export function deriveProjectStatus(
  repo: string,
  decisions: IssueSummary[],
  activity: ActivityEvent[],
): ProjectStatus {
  const repoDecisions = decisions.filter((d) => d.repo === repo);
  if (repoDecisions.length > 0) {
    return {
      repo,
      label: "needs-human-decision",
      subtitle: `${repoDecisions.length}件 起票`,
      decisionCount: repoDecisions.length,
    };
  }

  // activity は updated_at 降順に集約済み（orchestrator/aggregation.py）
  const latest = activity.find((a) => a.repo === repo);
  if (!latest) {
    return {
      repo,
      label: STATUS_TODO,
      subtitle: "issueなし",
      decisionCount: 0,
    };
  }

  const subtitle =
    latest.label === STATUS_TODO ? "キュー待ち" : `#${latest.number}`;
  return { repo, label: latest.label, subtitle, decisionCount: 0 };
}

export { shortRepoName };
