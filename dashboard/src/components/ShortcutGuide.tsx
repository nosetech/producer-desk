import { ISSUE_LIST_SHORTCUTS } from "@/lib/shortcuts";
import styles from "./ShortcutGuide.module.css";

/** ショートカットガイドでの表示単位（`ISSUE_LIST_SHORTCUTS`の`group`）ごとの説明。 */
const GROUP_LABELS: Record<string, string> = {
  move: "移動",
  select: "選択",
  clear: "選択解除",
  project: "プロジェクト",
  filter: "フィルタ",
  activate: "返信／計画",
};

/**
 * ガイドの`Enter`（返信／計画）の状態（issue #339）。`on`はカーソル行で効く（強調）、`off`は
 * カーソル行で効かない（薄くする）、`idle`はカーソルがない（通常表示）。
 */
export type EnterHint = "on" | "off" | "idle";

/**
 * ガイドでの表示順。`Enter`はカーソル行に対して働くため「移動」の直後に置く（デザイン
 * feature/issue-339-inbox-shortcuts の kbGuide）。それ以外は`ISSUE_LIST_SHORTCUTS`の順。
 */
const GROUP_ORDER = ["move", "activate"];

/** `kbd`に表示するキーの表記。Shift付きは`⇧H`の形、`Escape`は`Esc`、`Enter`は`↵`にする。 */
function keyText(key: string): string {
  if (key === "Escape") return "Esc";
  if (key === "Enter") return "↵";
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
  enterHint = "idle",
}: {
  hasSelection: boolean;
  enterHint?: EnterHint;
}) {
  const groups: { group: string; keys: string[] }[] = [];
  for (const s of ISSUE_LIST_SHORTCUTS) {
    const g = groups.find((x) => x.group === s.group);
    if (g) g.keys.push(s.key);
    else groups.push({ group: s.group, keys: [s.key] });
  }
  const rank = (g: string) => {
    const i = GROUP_ORDER.indexOf(g);
    return i < 0 ? GROUP_ORDER.length : i;
  };
  groups.sort((a, b) => rank(a.group) - rank(b.group));
  return (
    <div
      className={styles.guide}
      role="note"
      aria-label="キーボードショートカット"
    >
      <span className={styles.head}>キーボード</span>
      {groups.map(({ group, keys }, n) => {
        const hot =
          (group === "clear" && hasSelection) ||
          (group === "activate" && enterHint === "on");
        const off = group === "activate" && enterHint === "off";
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
                className={`${styles.kbd} ${hot ? styles.kbdHot : ""} ${off ? styles.kbdOff : ""}`}
                title={
                  off ? `${keyAria(k)} — この行では使えません` : keyAria(k)
                }
                aria-label={keyAria(k)}
              >
                {keyText(k)}
              </kbd>
            ))}
            <span
              className={`${styles.label} ${hot ? styles.labelHot : ""} ${off ? styles.labelOff : ""}`}
            >
              {GROUP_LABELS[group]}
            </span>
          </span>
        );
      })}
    </div>
  );
}
