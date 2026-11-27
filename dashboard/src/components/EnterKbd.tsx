import styles from "./EnterKbd.module.css";

/**
 * カーソル行で`Enter`を押すと実行されるボタン（issueの「返信する」、inboxの「計画する」）の右上に
 * 出す`↵`（issue #339、PC表示のみ）。置くボタンには`position: relative`が必要。
 */
export default function EnterKbd() {
  return (
    <kbd aria-hidden="true" className={styles.kbd}>
      ↵
    </kbd>
  );
}
