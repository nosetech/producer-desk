import {
  STATUS_IN_PROGRESS,
  STATUS_IN_REVIEW,
  STATUS_NEEDS_HUMAN_DECISION,
  STATUS_TODO,
  type StatusLabel,
} from "./status";

const VERB_BY_LABEL: Record<string, string> = {
  [STATUS_TODO]: "起票しました",
  [STATUS_IN_PROGRESS]: "着手しました",
  [STATUS_NEEDS_HUMAN_DECISION]: "判断待ちにしました",
  [STATUS_IN_REVIEW]: "レビュー待ちに移行しました",
};

export function activityVerb(label: StatusLabel): string {
  if (label === null) return "完了しました";
  return VERB_BY_LABEL[label] ?? "更新しました";
}
