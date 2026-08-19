import {
  STATUS_IN_PROGRESS,
  STATUS_IN_REVIEW,
  STATUS_NEEDS_HUMAN_DECISION,
  STATUS_TODO,
  statusCountMeta,
  statusMeta,
} from "@/lib/status";
import type { ProjectStatus } from "@/lib/projectStatus";
import { shortRepoName } from "@/lib/projectStatus";
import type { StatusCounts } from "@/lib/types";
import styles from "./ProjectStatusRow.module.css";

// 件数チップの表示順（0件のキーは表示しない、Claude Designの`SLK`に対応）。
const COUNT_ORDER: (keyof StatusCounts)[] = [
  STATUS_TODO,
  STATUS_IN_PROGRESS,
  STATUS_NEEDS_HUMAN_DECISION,
  STATUS_IN_REVIEW,
  "untagged",
];

function WarningIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}

function PlusIcon() {
  // Claude Designの実値(14px)より意図的に拡大（プラスの視認性向上のため、プロデューサーの明示的な指示）。
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export default function ProjectStatusRow({
  projects,
  onQuickCreate,
}: {
  projects: ProjectStatus[];
  onQuickCreate: (repo: string) => void;
}) {
  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <span className={styles.sectionTitle}>
          {projects.length} プロジェクト
        </span>
      </div>
      <div className={styles.row}>
        {projects.map((project) => {
          const meta = statusMeta(project.label);
          const countKeys = COUNT_ORDER.filter(
            (key) => project.counts[key] > 0,
          );
          return (
            <div key={project.repo} className={styles.chip}>
              <div className={styles.chipTop}>
                <span
                  className={styles.dot}
                  style={{ backgroundColor: `var(${meta.colorVar})` }}
                />
                <a
                  className={styles.repoName}
                  title={project.repo}
                  href={`https://github.com/${project.repo}/issues`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {shortRepoName(project.repo)}
                </a>
                {project.isOrphaned && (
                  <span
                    className={styles.orphanBadge}
                    title="作業中ラベルですが、対応するAgent Runnerが実行されていません（孤立状態の可能性があります）。"
                  >
                    <WarningIcon size={12} />
                  </span>
                )}
                <button
                  type="button"
                  className={styles.addButton}
                  onClick={() => onQuickCreate(project.repo)}
                  aria-label={`${project.repo}に新規タスクを作成`}
                  title="このプロジェクトに新規タスクを作成"
                >
                  <PlusIcon />
                </button>
              </div>
              <div className={styles.counts}>
                {countKeys.map((key) => {
                  const cMeta = statusCountMeta(key);
                  const isUntagged = key === "untagged";
                  const accent = isUntagged
                    ? { color: `var(${cMeta.colorVar})` }
                    : undefined;
                  return (
                    <div
                      key={key}
                      className={
                        isUntagged
                          ? `${styles.countCell} ${styles.countCellUntagged}`
                          : styles.countCell
                      }
                      title={`${cMeta.text} のissue ${project.counts[key]}件`}
                    >
                      {isUntagged ? (
                        <span className={styles.countIcon} style={accent}>
                          <WarningIcon size={11} />
                        </span>
                      ) : (
                        <span
                          className={styles.countDot}
                          style={{ backgroundColor: `var(${cMeta.colorVar})` }}
                        />
                      )}
                      <span className={styles.countLabel} style={accent}>
                        {cMeta.text}
                      </span>
                      <span className={styles.countValue} style={accent}>
                        {project.counts[key]}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
