"use client";

import styles from "./Toast.module.css";

export default function Toast({
  show,
  text,
  error = false,
  warn = false,
  quiet = false,
}: {
  show: boolean;
  text: string;
  error?: boolean;
  /** 一部失敗の警告（issue #305）。 */
  warn?: boolean;
  /** 控えめな通知（依頼の受付・計画の完了。issue #299）。 */
  quiet?: boolean;
}) {
  if (!show) return null;

  return (
    <div
      className={`${styles.toast} ${error ? styles.toastError : ""} ${warn && !error ? styles.toastWarn : ""} ${quiet && !error && !warn ? styles.toastQuiet : ""}`}
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
        {quiet && !error && !warn ? (
          <>
            <path d="M22 2 11 13" />
            <path d="M22 2 15 22l-4-9-9-4Z" />
          </>
        ) : error ? (
          <>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8v4M12 16h.01" />
          </>
        ) : warn ? (
          <>
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
            <path d="M12 9v4M12 17h.01" />
          </>
        ) : (
          <path d="M20 6 9 17l-5-5" />
        )}
      </svg>
      <span>{text}</span>
    </div>
  );
}
