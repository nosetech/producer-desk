import { activityVerb } from "@/lib/activityText";
import { statusMeta } from "@/lib/status";
import { formatRelativeTime } from "@/lib/time";
import { shortRepoName } from "@/lib/projectStatus";
import type { ActivityEvent } from "@/lib/types";
import styles from "./ActivityTimeline.module.css";

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
            return (
              <div
                key={`${event.repo}#${event.number}`}
                className={styles.item}
              >
                <span
                  className={styles.dot}
                  style={{ backgroundColor: `var(${meta.colorVar})` }}
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
