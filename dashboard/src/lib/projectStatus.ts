import { EMPTY_STATUS_COUNTS } from "./types";
import { STATUS_TODO, type StatusLabel } from "./status";
import type { IssueSummary, ProjectStatusSummary, StatusCounts } from "./types";

export interface ProjectStatus {
  repo: string;
  label: StatusLabel;
  isOrphaned: boolean;
  counts: StatusCounts;
}

function shortRepoName(repo: string): string {
  return repo.split("/")[1] ?? repo;
}

/**
 * リポジトリ単位の「並行状況」ウィジェット表示用データを組み立てる。
 *
 * `decisions`（判断待ち一覧）を最優先で反映するのは、直近更新issueが判断待ちで
 * なくても「対応が必要な判断待ちがある」ことをプロジェクト状態として常に目立たせる
 * ため（旧実装からの踏襲）。それ以外は`projectStatus`（オーケストレータの
 * `ProjectStatus`、issue #121でかつての横断タイムライン`activity`から置き換え）の
 * 直近更新issueの状態をそのまま使う。件数内訳・孤立in-progress検知は`label`の
 * 決定方法に依らず常に`projectStatus`由来の値を使う。
 */
export function deriveProjectStatus(
  repo: string,
  decisions: IssueSummary[],
  projectStatus: ProjectStatusSummary[],
): ProjectStatus {
  const status = projectStatus.find((p) => p.repo === repo);
  const counts = status?.counts ?? EMPTY_STATUS_COUNTS;
  const isOrphaned = status?.is_orphaned ?? false;

  const hasPendingDecision = decisions.some((d) => d.repo === repo);
  const label: StatusLabel = hasPendingDecision
    ? "needs-human-decision"
    : (status?.label ?? STATUS_TODO);

  return { repo, label, isOrphaned, counts };
}

export { shortRepoName };
