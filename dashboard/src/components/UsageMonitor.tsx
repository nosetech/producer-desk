import styles from "./UsageMonitor.module.css";

/**
 * Claude Codeの利用量/リミット取得方法は未実装（docs/basic-design.md 2-2で
 * 実装フェーズに設計を先送りされている）。実データ配信はissue #42に切り出し、
 * ここでは仮データである旨をUIに明示した上でモックのままにする（issue #32）。
 */
const MOCK_USAGE = {
  plan: "Max プラン",
  nearLimit: true,
  session: {
    label: "現在のセッション（5時間枠）",
    percent: 58,
    resetIn: "2時間14分後にリセット",
  },
  weekly: {
    label: "今週の利用上限",
    percent: 91,
    resetAt: "木曜 09:00にリセット・残りわずか",
  },
};

function barColor(percent: number): string {
  if (percent >= 85) return "var(--accent-red)";
  if (percent >= 60) return "var(--accent-amber)";
  return "var(--accent-blue)";
}

export default function UsageMonitor() {
  const { plan, nearLimit, session, weekly } = MOCK_USAGE;
  return (
    <div className={styles.panel}>
      <div className={styles.headerRow}>
        <span className={styles.titleGroup}>
          <span className={styles.title}>利用量 / リミット</span>
          <span className={styles.mockBadge}>仮データ表示中</span>
        </span>
        <span className={styles.plan}>{plan}</span>
      </div>
      <span className={styles.mockNote}>
        実データ配信は未実装のため、以下はサンプル値です。実際の利用率は Claude
        Code の <code className={styles.inlineCode}>/status</code> コマンドで
        確認してください（
        <a
          href="https://github.com/nosetech/producer-desk/issues/42"
          target="_blank"
          rel="noreferrer"
          className={styles.mockLink}
        >
          #42
        </a>
        ）。
      </span>

      {nearLimit && (
        <div className={styles.warning}>
          <span>⚠</span>
          <span>
            週間リミットが残りわずかです。到達すると
            <strong>Agent Runner は次のリセットまで待機</strong>
            します。
          </span>
        </div>
      )}

      <div className={styles.metric}>
        <div className={styles.metricHeader}>
          <span>{session.label}</span>
          <span className={styles.metricValue}>{session.percent}%</span>
        </div>
        <div className={styles.track}>
          <div
            className={styles.fill}
            style={{
              width: `${session.percent}%`,
              backgroundColor: barColor(session.percent),
            }}
          />
        </div>
        <span className={styles.footnote}>{session.resetIn}</span>
      </div>

      <div className={styles.metric}>
        <div className={styles.metricHeader}>
          <span>{weekly.label}</span>
          <span
            className={styles.metricValue}
            style={{ color: barColor(weekly.percent) }}
          >
            {weekly.percent}%
          </span>
        </div>
        <div className={styles.track}>
          <div
            className={styles.fill}
            style={{
              width: `${weekly.percent}%`,
              backgroundColor: barColor(weekly.percent),
            }}
          />
        </div>
        <span className={styles.footnote}>{weekly.resetAt}</span>
      </div>
    </div>
  );
}
