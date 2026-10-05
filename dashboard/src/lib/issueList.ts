import { STATUS_COUNT_UNTAGGED, statusCountMeta } from "./status";
import type { ProjectIssue } from "./types";

/** issue一覧の状態フィルタのキー。`all`/`orphan`以外は`issueStatusKey`の値に一致する。 */
export type IssueFilterKey = string;

export const FILTER_ALL = "all";
export const FILTER_ORPHAN = "orphan";

/** 状態フィルタの表示順（Claude Design ProducerDesk.dc.htmlの`FK`に対応）。 */
export const STATUS_FILTER_ORDER = [
  "status:todo",
  "status:in-progress",
  "needs-human-decision",
  "status:in-review",
  STATUS_COUNT_UNTAGGED,
  "status:closed",
] as const;

/** issueの状態キー（状態ラベル、タグなしは`untagged`）。 */
export function issueStatusKey(issue: ProjectIssue): string {
  return issue.label ?? STATUS_COUNT_UNTAGGED;
}

export function isClosed(issue: ProjectIssue): boolean {
  return issue.label === "status:closed";
}

export function issueStatusText(key: string): string {
  return key === "status:closed" ? "完了" : statusCountMeta(key).text;
}

export interface IssueFilterOption {
  key: IssueFilterKey;
  label: string;
  count: number;
}

export function buildFilterOptions(
  issues: ProjectIssue[],
  showDone: boolean,
): IssueFilterOption[] {
  const open = issues.filter((i) => !isClosed(i));
  const orphans = issues.filter((i) => i.is_orphaned);
  const options: IssueFilterOption[] = [
    {
      key: FILTER_ALL,
      label: "すべて",
      count: showDone ? issues.length : open.length,
    },
  ];
  if (orphans.length > 0) {
    options.push({
      key: FILTER_ORPHAN,
      label: "停止の可能性",
      count: orphans.length,
    });
  }
  for (const key of STATUS_FILTER_ORDER) {
    options.push({
      key,
      label: issueStatusText(key),
      count: issues.filter((i) => issueStatusKey(i) === key).length,
    });
  }
  return options;
}

export function filterIssues(
  issues: ProjectIssue[],
  filter: IssueFilterKey,
  showDone: boolean,
  sort: "desc" | "asc",
): ProjectIssue[] {
  let rows: ProjectIssue[];
  if (filter === FILTER_ALL) {
    rows = showDone ? issues : issues.filter((i) => !isClosed(i));
  } else if (filter === FILTER_ORPHAN) {
    rows = issues.filter((i) => i.is_orphaned);
  } else {
    rows = issues.filter((i) => issueStatusKey(i) === filter);
  }
  const dir = sort === "asc" ? 1 : -1;
  return rows
    .slice()
    .sort(
      (a, b) =>
        dir *
        (new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime()),
    );
}

/** `2026-10-05 13:24` 形式（ローカル時刻）。 */
export function formatAbsoluteTime(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
