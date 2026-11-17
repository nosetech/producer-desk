import type {
  IssuesMetaInput,
  IssuesMetaResult,
  MilestoneChange,
} from "./types";

/** サーバ側の一括変更の上限（orchestrator/issue_meta.py `MAX_META_ISSUES`）。 */
export const MAX_META_ISSUES = 100;

/** ヘッダーの「すべて選択」チェックボックスの状態。対象は現在のフィルタ後の表示行。 */
export type SelectAllState = "none" | "some" | "all";

export function selectAllState(
  visible: readonly number[],
  selected: ReadonlySet<number>,
): SelectAllState {
  if (visible.length === 0) return "none";
  const count = visible.filter((n) => selected.has(n)).length;
  if (count === 0) return "none";
  return count === visible.length ? "all" : "some";
}

export function toggleSelected(
  selected: ReadonlySet<number>,
  issueNumber: number,
): Set<number> {
  const next = new Set(selected);
  if (next.has(issueNumber)) next.delete(issueNumber);
  else next.add(issueNumber);
  return next;
}

/**
 * 「すべて選択」の切替。全選択済みなら表示行だけ解除、それ以外は表示行を全て選択する
 * （フィルタで非表示の選択済み行は維持する）。
 */
export function toggleSelectAll(
  visible: readonly number[],
  selected: ReadonlySet<number>,
): Set<number> {
  const next = new Set(selected);
  if (selectAllState(visible, selected) === "all") {
    for (const n of visible) next.delete(n);
  } else {
    for (const n of visible) next.add(n);
  }
  return next;
}

/** フィルタ変更や再取得で一覧から消えた行を選択から外す。 */
export function pruneSelection(
  selected: ReadonlySet<number>,
  existing: readonly number[],
): Set<number> {
  const exist = new Set(existing);
  return new Set([...selected].filter((n) => exist.has(n)));
}

/** 追加と削除の両方に同じラベルを指定できない。片方を選ぶともう片方から外す。 */
export function toggleLabelChoice(
  target: "add" | "remove",
  label: string,
  add: readonly string[],
  remove: readonly string[],
): { add: string[]; remove: string[] } {
  const own = target === "add" ? add : remove;
  const other = target === "add" ? remove : add;
  const nextOwn = own.includes(label)
    ? own.filter((l) => l !== label)
    : [...own, label];
  const nextOther = other.filter((l) => l !== label);
  return target === "add"
    ? { add: nextOwn, remove: nextOther }
    : { add: nextOther, remove: nextOwn };
}

export interface MetaDraft {
  milestone: MilestoneChange;
  addLabels: readonly string[];
  removeLabels: readonly string[];
}

/** 何も変更しない下書きは適用できない。 */
export function isMetaDraftEmpty(draft: MetaDraft): boolean {
  return (
    draft.milestone.mode === "keep" &&
    draft.addLabels.length === 0 &&
    draft.removeLabels.length === 0
  );
}

export function canApplyMeta(
  selected: ReadonlySet<number>,
  draft: MetaDraft,
): boolean {
  return (
    selected.size > 0 &&
    selected.size <= MAX_META_ISSUES &&
    !isMetaDraftEmpty(draft) &&
    (draft.milestone.mode !== "set" || draft.milestone.value !== "")
  );
}

export function buildMetaInput(
  selected: ReadonlySet<number>,
  draft: MetaDraft,
): IssuesMetaInput {
  return {
    issues: [...selected].sort((a, b) => a - b),
    milestone: draft.milestone,
    add_labels: [...draft.addLabels],
    remove_labels: [...draft.removeLabels],
  };
}

export interface MetaOutcome {
  /** 適用後も選択に残す番号（失敗分のみ）。 */
  remaining: Set<number>;
  /** 通知文。 */
  message: string;
  /** 一部でも失敗したか。 */
  hasFailure: boolean;
}

export function summarizeMetaResult(result: IssuesMetaResult): MetaOutcome {
  const ok = result.succeeded.length;
  const ng = result.failed.length;
  return {
    remaining: new Set(result.failed.map((f) => f.number)),
    hasFailure: ng > 0,
    message: ng === 0 ? `${ok}件を更新しました` : `${ok}件成功・${ng}件失敗`,
  };
}
