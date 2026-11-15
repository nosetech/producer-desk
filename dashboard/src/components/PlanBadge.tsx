import type { PlanJob, PlanJobErrorCode } from "@/lib/api";
import { planBadge } from "@/lib/planFlow";
import styles from "./PlanBadge.module.css";

// 計画の状態バッジ（issue #299）。
// デザイン: Artifactsの feature/issue-299-plan-background（_pBadge）。
// 色は キュー待ち=グレー / 計画中=青 / 確認待ち=黄 / 失敗=赤。

export const PLAN_ERR_SHORT: Record<PlanJobErrorCode, string> = {
  parse: "解釈不可",
  timeout: "タイムアウト",
  limit: "利用リミット",
  failed: "失敗",
  interrupted: "中断",
};

function label(job: PlanJob): string {
  switch (planBadge(job)) {
    case "queued":
      return `キュー待ち（${job.queuePosition ?? 1}番目）`;
    case "running":
      return "計画中";
    case "review":
      return "確認待ち";
    case "failed":
      return `失敗 · ${PLAN_ERR_SHORT[job.error?.code ?? "failed"] ?? "失敗"}`;
  }
}

function title(job: PlanJob): string {
  const revising = job.result !== null;
  switch (planBadge(job)) {
    case "queued":
      return `実行キューの${job.queuePosition ?? 1}番目で待機しています`;
    case "running":
      return revising
        ? "修正を反映中（直前の計画は残っています）"
        : "AIが計画を作成しています";
    case "review":
      return "計画ができました。内容を確認して承認してください";
    case "failed":
      return "計画の作成に失敗しました";
  }
}

function Glyph({ kind }: { kind: ReturnType<typeof planBadge> }) {
  if (kind === "running")
    return (
      <svg
        width="11"
        height="11"
        viewBox="0 0 42 42"
        aria-hidden
        className={styles.spin}
      >
        <circle
          cx="21"
          cy="21"
          r="17"
          fill="none"
          stroke="currentColor"
          strokeWidth="5"
          opacity=".28"
        />
        <circle
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
  const paths =
    kind === "queued"
      ? ["M12 7v5l3 2"]
      : kind === "review"
        ? [
            "M9 11l3 3 8-8",
            "M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9",
          ]
        : ["M12 8v4M12 16h.01"];
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      style={{ flex: "none" }}
    >
      {(kind === "queued" || kind === "failed") && (
        <circle cx="12" cy="12" r="9" />
      )}
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

const TONE = {
  queued: styles.queued,
  running: styles.running,
  review: styles.review,
  failed: styles.failed,
};

export default function PlanBadge({ job }: { job: PlanJob }) {
  const kind = planBadge(job);
  return (
    <span className={`${styles.badge} ${TONE[kind]}`} title={title(job)}>
      <Glyph kind={kind} />
      {label(job)}
    </span>
  );
}
