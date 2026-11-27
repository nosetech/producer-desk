/** 画面遷移ショートカットの割り当て（修飾キーなしの1キー、issue #251）。 */
export const NAV_SHORTCUTS = [
  { key: "d", href: "/", label: "ダッシュボード" },
  { key: "i", href: "/projects", label: "issue一覧" },
  { key: "p", href: "/prompts", label: "プロンプト設定" },
  { key: "s", href: "/snippets", label: "定型文" },
] as const;

export interface ShortcutEventLike {
  target: unknown;
  key: string;
  keyCode?: number;
  isComposing?: boolean;
  repeat?: boolean;
  defaultPrevented?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
}

const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

function isEditableTarget(target: unknown): boolean {
  if (!target || typeof target !== "object") return false;
  const el = target as { tagName?: string; isContentEditable?: boolean };
  return EDITABLE_TAGS.has(el.tagName ?? "") || el.isContentEditable === true;
}

export interface IgnoreShortcutOptions {
  /** Shift付きのキーを許可する（issue一覧の`H` / `L`、issue #322）。 */
  allowShift?: boolean;
  /** キーの押しっぱなし（repeat）を許可する（issue一覧の`j` / `k`の連続移動）。 */
  allowRepeat?: boolean;
  /**
   * ボタン・リンク等の操作できる要素にフォーカスがあるときも無視する（issue一覧の`Enter`、
   * issue #339）。そうした要素ではブラウザ本来の`Enter`動作（フォーカス中の要素を押す）を優先する。
   */
  ignoreOnInteractive?: boolean;
}

const INTERACTIVE_TAGS = new Set(["BUTTON", "A", "SUMMARY"]);

function isInteractiveTarget(target: unknown): boolean {
  if (!target || typeof target !== "object") return false;
  const el = target as { tagName?: string; getAttribute?: unknown };
  if (INTERACTIVE_TAGS.has(el.tagName ?? "")) return true;
  // `role="button"`等の、ボタンとして振る舞う要素も含める。
  if (typeof el.getAttribute === "function") {
    const role = (el.getAttribute as (n: string) => string | null).call(
      target,
      "role",
    );
    return (
      role === "button" ||
      role === "link" ||
      role === "menuitem" ||
      role === "option" ||
      role === "tab" ||
      role === "checkbox"
    );
  }
  return false;
}

/**
 * ショートカットを処理せず無視すべきかを判定する。文字入力中・IME変換中・修飾キー付き・
 * キー押しっぱなし・処理済みイベント・モーダル表示中（`modalOpen`）が対象。
 * Shift・押しっぱなしは`options`で個別に許可できる（既定は従来どおり無視）。
 */
export function shouldIgnoreShortcut(
  event: ShortcutEventLike,
  modalOpen = false,
  options: IgnoreShortcutOptions = {},
): boolean {
  return (
    modalOpen ||
    isEditableTarget(event.target) ||
    (options.ignoreOnInteractive === true &&
      isInteractiveTarget(event.target)) ||
    event.isComposing === true ||
    event.keyCode === 229 ||
    event.ctrlKey === true ||
    event.metaKey === true ||
    event.altKey === true ||
    (event.shiftKey === true && !options.allowShift) ||
    (event.repeat === true && !options.allowRepeat) ||
    event.defaultPrevented === true
  );
}

/** キーに対応する遷移先を返す（大文字小文字は区別しない）。 */
export function resolveShortcutHref(key: string): string | null {
  const lower = key.toLowerCase();
  return NAV_SHORTCUTS.find((s) => s.key === lower)?.href ?? null;
}

/** 現在のパスが遷移先と同じ画面か。 */
export function isSameScreen(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** issue一覧画面内のショートカットの動作（issue #322）。 */
export type IssueListAction =
  | "prevProject"
  | "nextProject"
  | "cursorDown"
  | "cursorUp"
  | "toggleSelect"
  | "clearSelection"
  | "prevFilter"
  | "nextFilter"
  | "activate";

/**
 * issue一覧画面のショートカットの割り当て（issue #322）。`key`は`KeyboardEvent.key`と完全一致で
 * 照合する（`H` / `L`はShift付き）。`group`はショートカットガイドでの表示単位。
 */
export const ISSUE_LIST_SHORTCUTS = [
  { key: "j", action: "cursorDown", label: "下へ", group: "move" },
  { key: "k", action: "cursorUp", label: "上へ", group: "move" },
  { key: "x", action: "toggleSelect", label: "選択", group: "select" },
  {
    key: "Escape",
    action: "clearSelection",
    label: "選択解除",
    group: "clear",
  },
  { key: "h", action: "prevProject", label: "前", group: "project" },
  { key: "l", action: "nextProject", label: "次", group: "project" },
  { key: "H", action: "prevFilter", label: "前", group: "filter" },
  { key: "L", action: "nextFilter", label: "次", group: "filter" },
  // カーソル行の主な操作（issueの行は「返信する」、inbox項目は「計画する」、issue #339）。
  { key: "Enter", action: "activate", label: "返信／計画", group: "activate" },
] as const satisfies readonly {
  key: string;
  action: IssueListAction;
  label: string;
  group: string;
}[];

/**
 * キーに対応するissue一覧画面の動作を返す（大文字小文字を区別する）。Shift付きで英小文字が
 * 届いた場合（CapsLock中のShift、一部の自動操作）は大文字として扱う。
 */
export function resolveIssueListAction(
  key: string,
  shiftKey = false,
): IssueListAction | null {
  const k = shiftKey && /^[a-z]$/.test(key) ? key.toUpperCase() : key;
  return ISSUE_LIST_SHORTCUTS.find((s) => s.key === k)?.action ?? null;
}

/** 動作に対応するキー（`aria-keyshortcuts`の値）。`H` / `L`は`Shift+H`の形にする。 */
export function ariaKeyShortcuts(...actions: IssueListAction[]): string {
  return ISSUE_LIST_SHORTCUTS.filter((s) =>
    (actions as string[]).includes(s.action),
  )
    .map((s) => (/^[A-Z]$/.test(s.key) ? `Shift+${s.key}` : s.key))
    .join(" ");
}

/**
 * `current`から`delta`だけ進めたインデックスを返す。端では止まる（回り込まない）。
 * `current`が-1（未選択）のときは、下向きなら先頭、上向きなら末尾から始める。
 * `length`が0ならnull。
 */
export function stepIndex(
  current: number,
  delta: number,
  length: number,
): number | null {
  if (length <= 0) return null;
  if (current < 0 || current >= length) return delta >= 0 ? 0 : length - 1;
  return Math.min(Math.max(current + delta, 0), length - 1);
}

/**
 * `j` / `k`で移動するカーソルの並び（issue #339）。inbox項目（`sortInbox`の順）→ issue一覧の行
 * （表示順）の1本の配列にする。inboxが折りたたまれている間（`inboxOpen`がfalse）はinbox項目を
 * 含めない。inboxとissueは同じリポジトリのissue番号なので重複しないが、念のため後勝ちで除く。
 */
export function cursorOrder(
  inboxNums: readonly number[],
  issueNums: readonly number[],
  inboxOpen: boolean,
): number[] {
  const head = inboxOpen ? inboxNums : [];
  const issues = new Set(issueNums);
  return [...head.filter((n) => !issues.has(n)), ...issueNums];
}

/**
 * 再取得・絞り込みでカーソル行が一覧から消えたときの移動先を決める。前回の表示順
 * （`prevOrder`）でカーソルより後ろにあった行のうち最も近い行、無ければ前にあった最も近い行。
 * どちらも無ければnull（未選択に戻す）。
 */
export function relocateCursor(
  cursor: number | null,
  prevOrder: readonly number[],
  nextOrder: readonly number[],
): number | null {
  if (cursor === null) return null;
  if (nextOrder.includes(cursor)) return cursor;
  const present = new Set(nextOrder);
  const at = prevOrder.indexOf(cursor);
  if (at < 0) return null;
  for (let i = at + 1; i < prevOrder.length; i++) {
    if (present.has(prevOrder[i])) return prevOrder[i];
  }
  for (let i = at - 1; i >= 0; i--) {
    if (present.has(prevOrder[i])) return prevOrder[i];
  }
  return null;
}
