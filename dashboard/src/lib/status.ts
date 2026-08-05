export const STATUS_TODO = "status:todo";
export const STATUS_IN_PROGRESS = "status:in-progress";
export const STATUS_NEEDS_HUMAN_DECISION = "needs-human-decision";
export const STATUS_IN_REVIEW = "status:in-review";

/** issueに付与される状態ラベル。nullはissueクローズ（完了）を表す。 */
export type StatusLabel =
  | typeof STATUS_TODO
  | typeof STATUS_IN_PROGRESS
  | typeof STATUS_NEEDS_HUMAN_DECISION
  | typeof STATUS_IN_REVIEW
  | null;

export interface StatusMeta {
  text: string;
  colorVar: string;
  bgVar: string;
}

const STATUS_META: Record<string, StatusMeta> = {
  [STATUS_TODO]: {
    text: "未着手",
    colorVar: "--accent-gray",
    bgVar: "--accent-gray-bg",
  },
  [STATUS_IN_PROGRESS]: {
    text: "作業中",
    colorVar: "--accent-blue",
    bgVar: "--accent-blue-bg",
  },
  [STATUS_NEEDS_HUMAN_DECISION]: {
    text: "判断待ち",
    colorVar: "--accent-amber",
    bgVar: "--accent-amber-bg",
  },
  [STATUS_IN_REVIEW]: {
    text: "レビュー待ち",
    colorVar: "--accent-purple",
    bgVar: "--accent-purple-bg",
  },
};

const DONE_META: StatusMeta = {
  text: "完了",
  colorVar: "--accent-green",
  bgVar: "--accent-green-bg",
};

const UNKNOWN_META: StatusMeta = {
  text: "未着手",
  colorVar: "--accent-gray",
  bgVar: "--accent-gray-bg",
};

export function statusMeta(label: string | null): StatusMeta {
  if (label === null) return DONE_META;
  return STATUS_META[label] ?? UNKNOWN_META;
}
