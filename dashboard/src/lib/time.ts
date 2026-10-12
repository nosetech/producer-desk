export function formatRelativeTime(
  isoString: string,
  now: Date = new Date(),
): string {
  const then = new Date(isoString);
  const diffMs = now.getTime() - then.getTime();
  const diffSec = Math.max(0, Math.floor(diffMs / 1000));

  if (diffSec < 60) return "たった今";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}分前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}時間前`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}日前`;
}

/** 「最終データ更新 YYYY-MM-DD HH:mm」形式のツールチップ文言（issue #197）。 */
export function formatSyncTitle(isoString: string): string {
  const d = new Date(isoString);
  const p = (n: number) => String(n).padStart(2, "0");
  return `最終データ更新 ${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
