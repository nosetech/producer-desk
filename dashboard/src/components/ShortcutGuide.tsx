import { ISSUE_LIST_SHORTCUTS } from "@/lib/shortcuts";
import styles from "./ShortcutGuide.module.css";

/** ショートカットガイドでの表示単位（`ISSUE_LIST_SHORTCUTS`の`group`）ごとの説明。 */
const GROUP_LABELS: Record<string, string> = {
  move: "移動",
  select: "選択",
  clear: "選択解除",
  project: "プロジェクト",
  filter: "フィルタ",
};

/** `kbd`に表示するキーの表記。Shift付きは`⇧H`の形、`Escape`は`Esc`にする。 */
function keyText(key: string): string {
  if (key === "Escape") return "Esc";
  return /^[A-Z]$/.test(key) ? `⇧${key}` : key;
}

/** 読み上げ・ツールチップ用の表記（`⇧H`は`Shift+H`）。 */
function keyAria(key: string): string {
  if (key === "Escape") return "Esc";
  return /^[A-Z]$/.test(key) ? `Shift+${key}` : key;
}

/**
 * issue一覧画面の下部に出すキーボードショートカットのガイド（issue #322、PC表示のみ）。
 * `hasSelection`のときは、今押せる「Esc 選択解除」を強調する。
 */
export default function ShortcutGuide({
  hasSelection,
}: {
  hasSelection: boolean;
}) {
  const groups: { group: string; keys: string[] }[] = [];
  for (const s of ISSUE_LIST_SHORTCUTS) {
    const g = groups.find((x) => x.group === s.group);
    if (g) g.keys.push(s.key);
    else groups.push({ group: s.group, keys: [s.key] });
  }
  return (
    <div
      className={styles.guide}
      role="note"
      aria-label="キーボードショートカット"
    >
      <span className={styles.head}>キーボード</span>
      {groups.map(({ group, keys }, n) => {
        const hot = group === "clear" && hasSelection;
        return (
          <span key={group} className={styles.item}>
            {n > 0 && (
              <span aria-hidden="true" className={styles.sep}>
                ·
              </span>
            )}
            {keys.map((k) => (
              <kbd
                key={k}
                className={`${styles.kbd} ${hot ? styles.kbdHot : ""}`}
                title={keyAria(k)}
                aria-label={keyAria(k)}
              >
                {keyText(k)}
              </kbd>
            ))}
            <span className={`${styles.label} ${hot ? styles.labelHot : ""}`}>
              {GROUP_LABELS[group]}
            </span>
          </span>
        );
      })}
    </div>
  );
}
