import type { ProjectQueue, QueueEntry } from "./types";

/** 待機アイコンの最大表示数。これを超える（+1件までは省略せず全部出す）と`+N`にまとめる。 */
export const QUEUE_MAX_SHOW = 4;

export type QueueDisplayItem =
  | { kind: "slot" }
  | { kind: "sep" }
  | { kind: "running"; key: string; entry: QueueEntry }
  | { kind: "waiting"; key: string; entry: QueueEntry; position: number }
  | { kind: "more"; count: number; labels: string[] };

/** AI計画ジョブのエントリか（issue #335）。 */
export function isPlanEntry(entry: QueueEntry): boolean {
  return entry.kind === "plan";
}

/** `+N`・aria-label用の短い表記。計画ジョブは負の内部番号を出さず「AI計画」とする。 */
export function queueEntryShortLabel(entry: QueueEntry): string {
  return isPlanEntry(entry) ? "AI計画" : `#${entry.number}`;
}

export function isQueueEmpty(queue: ProjectQueue): boolean {
  return queue.running === null && queue.waiting.length === 0;
}

/**
 * キューのレーンに並べる要素を組み立てる（Claude Designの`buildQueue`に対応）。
 * 実行中を先頭に置き（無ければ空き枠）、待機中をFIFO順に続ける。待機が
 * `QUEUE_MAX_SHOW + 1`件を超える場合は先頭`QUEUE_MAX_SHOW`件＋`+N`にまとめる
 * （`+1`だけ余る場合は`+1`にせず全部出す）。空キューは要素なし（空のレーン枠のみ）。
 */
export function buildQueueItems(queue: ProjectQueue): QueueDisplayItem[] {
  if (isQueueEmpty(queue)) return [];
  const items: QueueDisplayItem[] = [];
  if (queue.running) {
    items.push({ kind: "running", key: "r", entry: queue.running });
  } else {
    items.push({ kind: "slot" });
  }
  if (queue.waiting.length > 0) items.push({ kind: "sep" });
  const over = queue.waiting.length > QUEUE_MAX_SHOW + 1;
  const shown = over ? queue.waiting.slice(0, QUEUE_MAX_SHOW) : queue.waiting;
  shown.forEach((entry, i) =>
    items.push({ kind: "waiting", key: `w${i}`, entry, position: i + 1 }),
  );
  if (over) {
    const rest = queue.waiting.slice(shown.length);
    items.push({
      kind: "more",
      count: rest.length,
      labels: rest.map(queueEntryShortLabel),
    });
  }
  return items;
}

export function queueAriaLabel(repo: string, queue: ProjectQueue): string {
  if (isQueueEmpty(queue)) return `${repo} の実行キュー: 空`;
  const running = queue.running
    ? `実行中 ${queueEntryShortLabel(queue.running)}、`
    : "実行中なし、";
  // デザイン（issue #335）どおり、待機中の計画ジョブの件数を添える。
  const planWaiting = queue.waiting.filter(isPlanEntry).length;
  const plans = planWaiting > 0 ? `（うちAI計画 ${planWaiting}件）` : "";
  return `${repo} の実行キュー: ${running}待機 ${queue.waiting.length}件${plans}`;
}

/** タスクアイコンの読み上げ。計画ジョブは負の内部番号を出さず「AI計画」とする。 */
export function queueEntryAriaLabel(
  entry: QueueEntry,
  posText: string,
): string {
  if (isPlanEntry(entry)) {
    const want = entry.title ? ` ${truncateQueueTitle(entry.title)}` : "";
    return `AI計画${want} — ${posText}`;
  }
  return `#${entry.number}${entry.title !== null ? ` ${entry.title}` : ""} — ${posText}`;
}

/** ピン留め時の計画ジョブの案内（「計画を開く」を出せない場合）。 */
export function planOpenHint(entry: QueueEntry): string {
  return entry.inbox_issue_number != null
    ? "完成すると inbox の「計画を開く」から確認できます"
    : "完成すると、新規作成の「未承認の計画」から確認できます";
}

/** 計画ジョブから計画確認パネルを開けるか（inbox由来で既に計画を持つ＝修正中のみ）。 */
export function canOpenPlan(entry: QueueEntry): boolean {
  return (
    isPlanEntry(entry) &&
    entry.inbox_issue_number != null &&
    entry.plan_revising === true
  );
}

export function queuePositionText(
  isRunning: boolean,
  position: number,
): string {
  return isRunning ? "実行中" : `待機中 · ${position}番目`;
}

/** ツールチップのタイトルを44文字で省略する。 */
export function truncateQueueTitle(title: string): string {
  return title.length > 44 ? `${title.slice(0, 43)}…` : title;
}
