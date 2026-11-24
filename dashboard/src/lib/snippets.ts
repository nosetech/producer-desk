// 返信欄の定型文（issue #323）のクライアント側ロジック。検証の上限値はオーケストレータの
// orchestrator/orchestrator/snippets.py（MAX_TITLE_LENGTH等）と揃える。

export const MAX_SNIPPET_TITLE_LENGTH = 50;
export const MAX_SNIPPET_BODY_LENGTH = 2000;
export const MAX_SNIPPETS = 50;

/**
 * `text`の`start`〜`end`（textareaのselectionStart/selectionEnd）を`snippet`で置き換え、
 * 置換後の本文と挿入文末尾のカーソル位置を返す。範囲外・逆転した位置は丸める。
 */
export function insertAtCursor(
  text: string,
  start: number,
  end: number,
  snippet: string,
): { text: string; cursor: number } {
  const s = Math.max(0, Math.min(start, text.length));
  const e = Math.max(s, Math.min(end, text.length));
  return {
    text: text.slice(0, s) + snippet + text.slice(e),
    cursor: s + snippet.length,
  };
}

/** 文字数（サロゲートペアを1文字と数える。オーケストレータの`len()`と揃える）。 */
export function charCount(text: string): number {
  return [...text].length;
}

export interface SnippetDraftCheck {
  ok: boolean;
  titleError: string | null;
  bodyError: string | null;
  titleLength: number;
  bodyLength: number;
}

/** 編集フォームの検証（デザイン feature/issue-323-snippets の`_snCheck`に対応）。 */
export function checkSnippetDraft(
  title: string,
  body: string,
): SnippetDraftCheck {
  const titleLength = charCount(title);
  const bodyLength = charCount(body);
  let titleError: string | null = null;
  let bodyError: string | null = null;
  if (!title.trim()) titleError = "タイトルを入力してください";
  else if (titleLength > MAX_SNIPPET_TITLE_LENGTH)
    titleError = `タイトルは${MAX_SNIPPET_TITLE_LENGTH}文字以内にしてください（現在 ${titleLength}文字）`;
  if (!body.trim()) bodyError = "本文を入力してください";
  else if (bodyLength > MAX_SNIPPET_BODY_LENGTH)
    bodyError = `本文は${MAX_SNIPPET_BODY_LENGTH.toLocaleString()}文字以内にしてください（現在 ${bodyLength.toLocaleString()}文字）`;
  return {
    ok: !titleError && !bodyError,
    titleError,
    bodyError,
    titleLength,
    bodyLength,
  };
}

/** 一覧表示用の本文の先頭1行。 */
export function firstLine(body: string): string {
  return body.split("\n").find((line) => line.trim()) ?? "";
}

/** `ids`の`index`番目を`delta`（±1）だけ移動した新しい配列。範囲外なら同じ配列を返す。 */
export function moveItem<T>(items: T[], index: number, delta: number): T[] {
  const to = index + delta;
  if (index < 0 || index >= items.length || to < 0 || to >= items.length)
    return items;
  const next = items.slice();
  const [item] = next.splice(index, 1);
  next.splice(to, 0, item);
  return next;
}
