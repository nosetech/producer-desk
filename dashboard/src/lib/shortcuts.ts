/** 画面遷移ショートカットの割り当て（修飾キーなしの1キー、issue #251）。 */
export const NAV_SHORTCUTS = [
  { key: "d", href: "/", label: "ダッシュボード" },
  { key: "i", href: "/projects", label: "issue一覧" },
  { key: "p", href: "/prompts", label: "プロンプト設定" },
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

/**
 * ショートカットを処理せず無視すべきかを判定する。文字入力中・IME変換中・修飾キー付き・
 * キー押しっぱなし・処理済みイベント・モーダル表示中（`modalOpen`）が対象。
 */
export function shouldIgnoreShortcut(
  event: ShortcutEventLike,
  modalOpen = false,
): boolean {
  return (
    modalOpen ||
    isEditableTarget(event.target) ||
    event.isComposing === true ||
    event.keyCode === 229 ||
    event.ctrlKey === true ||
    event.metaKey === true ||
    event.altKey === true ||
    event.shiftKey === true ||
    event.repeat === true ||
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
