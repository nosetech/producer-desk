import { statusMeta, type StatusLabel } from "@/lib/status";
import styles from "./StatusBadge.module.css";

export default function StatusBadge({ label }: { label: StatusLabel }) {
  const meta = statusMeta(label);
  return (
    <span
      className={styles.badge}
      style={{
        color: `var(${meta.colorVar})`,
        backgroundColor: `var(${meta.bgVar})`,
      }}
    >
      {meta.text}
    </span>
  );
}
