"use client";

import styles from "./Toast.module.css";

export default function Toast({
  show,
  text,
  error = false,
}: {
  show: boolean;
  text: string;
  error?: boolean;
}) {
  if (!show) return null;

  return (
    <div
      className={`${styles.toast} ${error ? styles.toastError : ""}`}
      role={error ? "alert" : "status"}
    >
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
        {error ? (
          <>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8v4M12 16h.01" />
          </>
        ) : (
          <path d="M20 6 9 17l-5-5" />
        )}
      </svg>
      <span>{text}</span>
    </div>
  );
}
