// 判断待ちカードの「利用リミット待ち」表示（issue #331）の表示用ヘルパー。

const MIN = 60 * 1000;

/** 自動再開予定時刻を`M/D HH:mm`（ブラウザのローカル時刻）で表す。 */
export function formatResetAt(ms: number): string {
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 残り時間を「あと2時間15分」「あと5分」「あと1分未満」の形で表す。 */
export function formatTimeLeft(ms: number): string {
  const m = Math.max(0, Math.ceil(ms / MIN));
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (h) return `あと${h}時間${r ? `${r}分` : ""}`;
  return r ? `あと${r}分` : "あと1分未満";
}

/** 「別モデルで今すぐ再開」で投稿するコメント本文（`/model`行＋再開の指示）。 */
export function limitResumeMessage(alias: string): string {
  return `/model litellm:${alias}\n\n利用リミットの解除を待たずに、このモデルで作業を再開してください。`;
}
