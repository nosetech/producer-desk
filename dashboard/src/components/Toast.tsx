"use client";

import styles from "./Toast.module.css";

export default function Toast({ show, text }: { show: boolean; text: string }) {
  if (!show) return null;

  return (
    <div className={styles.toast} role="status">
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={styles.icon}
      >
        <path d="M20 6 9 17l-5-5" />
      </svg>
      <span>{text}</span>
    </div>
  );
}
