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

/** 編集フォームの検証。エラーメッセージの配列を返す（空なら保存可能）。 */
export function validateSnippetDraft(title: string, body: string): string[] {
  const errors: string[] = [];
  if (!title.trim()) errors.push("タイトルが空です");
  else if (/[\r\n]/.test(title)) errors.push("タイトルに改行は使用できません");
  else if (title.trim().length > MAX_SNIPPET_TITLE_LENGTH)
    errors.push(
      `タイトルは${MAX_SNIPPET_TITLE_LENGTH}文字以内にしてください`,
    );
  if (!body.trim()) errors.push("本文が空です");
  else if (body.length > MAX_SNIPPET_BODY_LENGTH)
    errors.push(`本文は${MAX_SNIPPET_BODY_LENGTH}文字以内にしてください`);
  return errors;
}

/** 一覧表示用の本文の先頭1行。 */
export function firstLine(body: string): string {
  return body.trimStart().split("\n", 1)[0] ?? "";
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
