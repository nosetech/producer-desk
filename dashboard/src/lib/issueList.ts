import { STATUS_COUNT_UNTAGGED, statusCountMeta } from "./status";
import type { ProjectIssue } from "./types";

/** issue一覧の状態フィルタのキー。`all`/`orphan`以外は`issueStatusKey`の値に一致する。 */
export type IssueFilterKey = string;

export const FILTER_ALL = "all";
export const FILTER_ORPHAN = "orphan";
/** issue一覧を開いた直後の初期フィルタ（未着手）。 */
export const DEFAULT_FILTER = "status:todo";

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
  const options: IssueFilterOption[] = [];
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
  options.push({
    key: FILTER_ALL,
    label: "すべて",
    count: showDone ? issues.length : open.length,
  });
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

/** マイルストーン/タグ条件の結合モード（issue #303）。 */
export type MatchMode = "or" | "and";

/** マイルストーン/タグの選択肢。`value`は一覧の値そのもの。 */
export interface MetaFilterOption {
  value: string;
  count: number;
}

export function issueTags(issue: ProjectIssue): string[] {
  return issue.tags ?? [];
}

/**
 * マイルストーン・タグの選択肢を返す。選択肢の集合・並びは`issues`全体から決め
 * （マイルストーンは名前順、タグは件数の多い順）、件数は`counted`（状態フィルタ後の
 * 一覧。省略時は`issues`）で数える。マイルストーンは`openMilestones`（オープン中の
 * タイトル一覧、issue #308）に含まれるものだけを選択肢にする。`null`・省略時は
 * 絞り込まない（取得失敗時の従来動作）。
 */
export function buildMetaFilterOptions(
  issues: ProjectIssue[],
  counted: ProjectIssue[] = issues,
  openMilestones: readonly string[] | null = null,
): {
  milestones: MetaFilterOption[];
  tags: MetaFilterOption[];
} {
  const milestoneNames = new Set<string>();
  const tagFreq = new Map<string, number>();
  for (const issue of issues) {
    if (
      issue.milestone &&
      (openMilestones === null || openMilestones.includes(issue.milestone))
    ) {
      milestoneNames.add(issue.milestone);
    }
    for (const tag of new Set(issueTags(issue))) {
      tagFreq.set(tag, (tagFreq.get(tag) ?? 0) + 1);
    }
  }
  const milestones = [...milestoneNames]
    .sort((a, b) => a.localeCompare(b, "ja", { numeric: true }))
    .map((value) => ({
      value,
      count: counted.filter((i) => i.milestone === value).length,
    }));
  const tags = [...tagFreq.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value]) => ({
      value,
      count: counted.filter((i) => issueTags(i).includes(value)).length,
    }));
  return { milestones, tags };
}

/**
 * マイルストーン/タグ条件で絞り込む。選択が0件なら絞り込まない。
 * ORは選択条件のいずれか、ANDはすべてに該当するissueを残す。
 * issueのマイルストーンは1つだけなので、ANDで複数のマイルストーンを選ぶと0件になる。
 */
export function filterByMeta(
  issues: ProjectIssue[],
  milestones: string[],
  tags: string[],
  mode: MatchMode,
): ProjectIssue[] {
  if (milestones.length + tags.length === 0) return issues;
  return issues.filter((issue) => {
    const own = new Set(issueTags(issue));
    const hits = [
      ...milestones.map((m) => issue.milestone === m),
      ...tags.map((t) => own.has(t)),
    ];
    return mode === "and" ? hits.every(Boolean) : hits.some(Boolean);
  });
}
