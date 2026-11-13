// inbox（バグ・機能アイデアの一行メモ置き場、issue #288）の表示・入力ロジック。
// UI・通信から切り離してテストできるよう純粋関数にまとめる。

import type { InboxItem, InboxKind } from "./types";

export interface InboxKindMeta {
  kind: InboxKind;
  label: string;
  /** バッジの文字色・背景色（globals.cssの変数名）。 */
  colorVar: string;
  bgVar: string;
}

export const INBOX_KINDS: readonly InboxKindMeta[] = [
  { kind: "bug", label: "バグ", colorVar: "--warn", bgVar: "--warn-bg" },
  {
    kind: "enhancement",
    label: "機能アイデア",
    colorVar: "--accent-blue",
    bgVar: "--accent-blue-bg",
  },
  {
    kind: "other",
    label: "その他",
    colorVar: "--accent-gray",
    bgVar: "--accent-gray-bg",
  },
];

/** 登録フォームの既定の種別。 */
export const DEFAULT_INBOX_KIND: InboxKind = "enhancement";

export const INBOX_TITLE_MAX = 120;

export function inboxKindMeta(kind: InboxKind): InboxKindMeta {
  return INBOX_KINDS.find((k) => k.kind === kind) ?? INBOX_KINDS[2];
}

export interface InboxDraft {
  kind: InboxKind | "";
  title: string;
  body: string;
}

/** 種別（3択のいずれか）と一言メモが揃っているときだけ登録・保存できる。 */
export function canSubmitInbox(draft: InboxDraft): boolean {
  return (
    INBOX_KINDS.some((k) => k.kind === draft.kind) &&
    draft.title.trim().length > 0 &&
    draft.title.length <= INBOX_TITLE_MAX
  );
}

/** 登録日時の新しい順（同時刻はissue番号の大きい順）に並べる。 */
export function sortInbox(items: readonly InboxItem[]): InboxItem[] {
  return [...items].sort(
    (a, b) => b.created_at.localeCompare(a.created_at) || b.number - a.number,
  );
}
