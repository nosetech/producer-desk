export const STATUS_TODO = "status:todo";
export const STATUS_IN_PROGRESS = "status:in-progress";
export const STATUS_NEEDS_HUMAN_DECISION = "needs-human-decision";
export const STATUS_IN_REVIEW = "status:in-review";
export const STATUS_CLOSED = "status:closed";

/**
 * issueに付与される状態ラベル。producer-deskが管理するissueは常にこの5つの
 * いずれか1つを持つ（いずれも付いていないissueは管理対象外としてAPI応答に
 * 含まれない。docs/basic-design.md 1章「管理対象外issueの扱い」）。
 */
export type StatusLabel =
  | typeof STATUS_TODO
  | typeof STATUS_IN_PROGRESS
  | typeof STATUS_NEEDS_HUMAN_DECISION
  | typeof STATUS_IN_REVIEW
  | typeof STATUS_CLOSED;

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
  [STATUS_CLOSED]: {
    text: "完了",
    colorVar: "--accent-green",
    bgVar: "--accent-green-bg",
  },
};

const UNKNOWN_META: StatusMeta = {
  text: "未着手",
  colorVar: "--accent-gray",
  bgVar: "--accent-gray-bg",
};

export function statusMeta(label: string): StatusMeta {
  return STATUS_META[label] ?? UNKNOWN_META;
}
