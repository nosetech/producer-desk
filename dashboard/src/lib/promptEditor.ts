import type { PromptInfo } from "./types";

/** プレースホルダ形式（`{識別子}`）。JSON例示の`{"a": 1}`は識別子形式ではないため対象外。
 * オーケストレータ`prompts.py`の検証と同じ規則。 */
const PLACEHOLDER_PATTERN = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

export interface PromptCheck {
  /** 本文に含まれていない必須トークン。 */
  missing: string[];
  /** 許可されていないプレースホルダ名（波括弧なし）。 */
  unknown: string[];
  empty: boolean;
  ok: boolean;
}

/** 保存前の検証。オーケストレータ側（`validate_prompt_text`）と同じ規則で、保存可否を即時に表示するために使う。 */
export function checkPrompt(
  prompt: Pick<PromptInfo, "required_tokens" | "placeholders">,
  text: string,
): PromptCheck {
  const missing = prompt.required_tokens
    .filter((t) => !text.includes(t.token))
    .map((t) => t.token);
  const unknown = [
    ...new Set(
      [...text.matchAll(PLACEHOLDER_PATTERN)]
        .map((m) => m[1])
        .filter((n) => !prompt.placeholders.includes(n)),
    ),
  ];
  const empty = text.trim() === "";
  return {
    missing,
    unknown,
    empty,
    ok: missing.length === 0 && unknown.length === 0 && !empty,
  };
}

export type DiffSign = " " | "-" | "+";

/** 行単位のLCS差分（デフォルト → 現在の内容）。 */
export function diffLines(a: string, b: string): [DiffSign, string][] {
  const A = a.split("\n");
  const B = b.split("\n");
  const n = A.length;
  const m = B.length;
  const L = Array.from({ length: n + 1 }, () =>
    new Array<number>(m + 1).fill(0),
  );
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      L[i][j] =
        A[i] === B[j]
          ? L[i + 1][j + 1] + 1
          : Math.max(L[i + 1][j], L[i][j + 1]);
    }
  }
  const out: [DiffSign, string][] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) {
      out.push([" ", A[i]]);
      i++;
      j++;
    } else if (L[i + 1][j] >= L[i][j + 1]) {
      out.push(["-", A[i++]]);
    } else {
      out.push(["+", B[j++]]);
    }
  }
  while (i < n) out.push(["-", A[i++]]);
  while (j < m) out.push(["+", B[j++]]);
  return out;
}
