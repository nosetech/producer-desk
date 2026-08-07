import { statusMeta } from "@/lib/status";
import type { ProjectStatus } from "@/lib/projectStatus";
import { shortRepoName } from "@/lib/projectStatus";
import styles from "./ProjectStatusRow.module.css";

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
        <span className={styles.sectionTitle}>並行状況</span>
        <span className={styles.sectionCount}>
          {projects.length} プロジェクト
        </span>
      </div>
      <div className={styles.row}>
        {projects.map((project) => {
          const meta = statusMeta(project.label);
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
                <button
                  type="button"
                  className={styles.addButton}
                  onClick={() => onQuickCreate(project.repo)}
                  aria-label={`${project.repo}に新規タスクを作成`}
                  title="このプロジェクトに新規タスクを作成"
                >
                  +
                </button>
              </div>
              <div className={styles.chipBottom}>
                <span
                  style={{
                    color: `var(${meta.colorVar})`,
                    fontSize: "0.78rem",
                    fontWeight: 600,
                  }}
                >
                  {meta.text}
                </span>
                <span className={styles.subtitle}>{project.subtitle}</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
