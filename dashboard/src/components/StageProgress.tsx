import type { ResolvedStage } from "@/lib/stageProgress";
import styles from "./StageProgress.module.css";

// ボタンに埋め込む段階リングスピナー（Claude Design SendingSpinner.dc.html
// 「1C 段階リング」/ feature/issue-167-approve-progress.dc.html 共通）。
// strokeにcurrentColorを使うため、緑・青どちらのボタン上でも配色トークンを
// 持ち込まずに済む。trackOpacityはボタンごとの実測値（Composerの送信ボタンは
// .32、承認系の確認ダイアログボタンは.34）をそのまま反映する。
export function SpinnerIcon({ trackOpacity }: { trackOpacity?: number }) {
  return (
    <svg
      className={styles.spinnerSvg}
      width="15"
      height="15"
      viewBox="0 0 42 42"
    >
      <circle
        className={styles.spinnerTrack}
        style={trackOpacity != null ? { opacity: trackOpacity } : undefined}
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
      />
      <circle
        className={styles.spinnerArc}
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray="34 200"
      />
    </svg>
  );
}

function RowIcon({ state }: { state: ResolvedStage["state"] }) {
  if (state === "done") {
    return (
      <svg
        className={styles.stageDot}
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="var(--accent-green)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M20 6 9 17l-5-5" />
      </svg>
    );
  }
  if (state === "active") {
    return (
      <svg
        className={`${styles.stageDot} ${styles.stageActiveSpinner}`}
        width="15"
        height="15"
        viewBox="0 0 42 42"
      >
        <circle
          cx="21"
          cy="21"
          r="17"
          fill="none"
          stroke="currentColor"
          strokeWidth="5"
          opacity="0.26"
        />
        <circle
          className={styles.spinnerArc}
          cx="21"
          cy="21"
          r="17"
          fill="none"
          stroke="currentColor"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray="34 200"
        />
      </svg>
    );
  }
  if (state === "skipped") {
    return (
      <svg
        className={styles.stageDot}
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="var(--text-tertiary)"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M20 6 9 17l-5-5" />
        <path d="M3 21 21 3" />
      </svg>
    );
  }
  if (state === "failed") {
    return (
      <svg
        className={styles.stageDot}
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="var(--warn)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v6M12 16.5v.01" />
      </svg>
    );
  }
  return (
    <span className={styles.stageDot}>
      <span className={styles.stageDotPending} />
    </span>
  );
}

export function StageList({ stages }: { stages: ResolvedStage[] }) {
  return (
    <div className={styles.stagePanel}>
      {stages.map((s) => (
        <div
          className={`${styles.stageRow} ${
            s.state === "skipped" ? styles.stageRowSkipped : ""
          }`}
          key={s.key}
        >
          <RowIcon state={s.state} />
          <span
            className={`${styles.stageLabel} ${
              s.state === "active"
                ? styles.stageLabelActive
                : s.state === "pending"
                  ? styles.stageLabelPending
                  : s.state === "skipped"
                    ? styles.stageLabelSkipped
                    : s.state === "failed"
                      ? styles.stageLabelFailed
                      : styles.stageLabelDone
            }`}
          >
            {s.label}
          </span>
          <span className={styles.stageLine} />
          <span
            className={`${styles.stageNote} ${
              s.state === "failed" ? styles.stageNoteFailed : ""
            }`}
          >
            {s.state === "skipped"
              ? "スキップ"
              : s.state === "failed"
                ? "失敗"
                : s.note}
          </span>
        </div>
      ))}
    </div>
  );
}
