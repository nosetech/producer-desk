import { activityVerb } from "@/lib/activityText";
import { STATUS_IN_PROGRESS, statusMeta } from "@/lib/status";
import { formatRelativeTime } from "@/lib/time";
import { shortRepoName } from "@/lib/projectStatus";
import type { ActivityEvent } from "@/lib/types";
import styles from "./ActivityTimeline.module.css";

function WarningIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={styles.warningIcon}
    >
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}

function RunningIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={styles.runningIcon}
    >
      <path d="M12 2v4" />
      <path d="m16.2 7.8 2.9-2.9" />
      <path d="M18 12h4" />
      <path d="m16.2 16.2 2.9 2.9" />
      <path d="M12 18v4" />
      <path d="m4.9 19.1 2.9-2.9" />
      <path d="M2 12h4" />
      <path d="m4.9 4.9 2.9 2.9" />
    </svg>
  );
}

export default function ActivityTimeline({
  activity,
  onReply,
}: {
  activity: ActivityEvent[];
  onReply: (repo: string, issueNumber: number, title: string) => void;
}) {
  return (
    <div className={styles.panel}>
      <div className={styles.headerRow}>
        <span className={styles.title}>最近の活動</span>
        <span className={styles.subtitle}>横断タイムライン</span>
      </div>
      {activity.length === 0 ? (
        <div className={styles.empty}>まだ活動はありません</div>
      ) : (
        <div className={styles.list}>
          {activity.map((event) => {
            const meta = statusMeta(event.label);
            const dotColorVar = event.is_orphaned
              ? "--accent-red"
              : meta.colorVar;
            return (
              <div
                key={`${event.repo}#${event.number}`}
                className={styles.item}
              >
                <span
                  className={styles.dot}
                  style={{ backgroundColor: `var(${dotColorVar})` }}
                />
                <div className={styles.text}>
                  <span className={styles.repoLabel}>
                    {shortRepoName(event.repo)}
                  </span>{" "}
                  が「
                  {event.title}」を{activityVerb(event.label)}
                  <div className={styles.time}>
                    {formatRelativeTime(event.updated_at)}
                  </div>
                  {event.is_orphaned && (
                    <div className={styles.warningBox}>
                      <WarningIcon />
                      <div className={styles.warningTextGroup}>
                        <div className={styles.warningTitle}>
                          実行中プロセスが見つかりません
                        </div>
                        <div className={styles.warningDesc}>
                          ラベルは{" "}
                          <span className={styles.warningCode}>
                            status:in-progress
                          </span>{" "}
                          ですが、Agent Runner
                          のプロセスが起動していません（孤立状態）。
                        </div>
                      </div>
                    </div>
                  )}
                  {event.label === STATUS_IN_PROGRESS && !event.is_orphaned && (
                    <div className={styles.runningBox}>
                      <RunningIcon />
                      <span className={styles.runningText}>
                        Agent Runner が実行中です
                      </span>
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  className={styles.replyBtn}
                  onClick={() => onReply(event.repo, event.number, event.title)}
                  aria-label={`#${event.number} に返信`}
                  title="返信"
                >
                  ↩
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
