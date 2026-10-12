import styles from "./RefreshButton.module.css";

/**
 * 再取得ボタン（Claude Design ProducerDesk.dc.htmlの`refreshBtnStyle`/`dashRefreshBtnStyle`。
 * issue #197）。`size`が`md`ならissue一覧画面（30px/モバイル40px）、`sm`ならダッシュボード
 * 画面（24px/モバイル36px）向け。取得中はアイコンを回転させ、無効化する。
 */
export default function RefreshButton({
  size,
  refreshing,
  title,
  onClick,
}: {
  size: "sm" | "md";
  refreshing: boolean;
  title: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`${styles.button} ${size === "md" ? styles.md : styles.sm}`}
      disabled={refreshing}
      aria-label="再取得"
      aria-busy={refreshing}
      title={title}
      onClick={onClick}
    >
      <svg
        width={size === "md" ? 14 : 13}
        height={size === "md" ? 14 : 13}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`${styles.icon} ${refreshing ? styles.spin : ""}`}
        aria-hidden="true"
      >
        <path d="M21 12a9 9 0 1 1-2.64-6.36" />
        <path d="M21 3v6h-6" />
      </svg>
    </button>
  );
}
