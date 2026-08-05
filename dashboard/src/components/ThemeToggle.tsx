"use client";

import { useEffect, useState } from "react";
import styles from "./ThemeToggle.module.css";

type Theme = "light" | "dark";

function currentTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "light" || attr === "dark") return attr;
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    // documentのdata-theme属性（layout.tsxのインラインスクリプトが設定）はSSR時に
    // 参照できないため、マウント後に一度だけ実際の値へ同期する。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(currentTheme());

    // 手動で切り替えていない（data-theme未設定）場合は、OSのテーマ設定が
    // タブを開いたまま変わったときもアイコン表示をリアルタイムに追従させる。
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const handleChange = () => setTheme(currentTheme());
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  }

  const label =
    theme === "dark" ? "ライトモードに切り替え" : "ダークモードに切り替え";

  return (
    <button
      type="button"
      className={styles.button}
      onClick={toggle}
      aria-label={label}
      title={label}
    >
      {theme === "dark" ? (
        <svg
          className={styles.icon}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>
      ) : (
        <svg className={styles.icon} viewBox="0 0 24 24" fill="currentColor">
          <path d="M20.742 13.045a8.088 8.088 0 0 1-2.077.273c-4.508 0-8.16-3.653-8.16-8.16 0-.727.096-1.432.273-2.078a.5.5 0 0 0-.7-.6A9.66 9.66 0 0 0 3 11a9.5 9.5 0 0 0 9.5 9.5 9.66 9.66 0 0 0 8.42-4.955.5.5 0 0 0-.178-.5Z" />
        </svg>
      )}
    </button>
  );
}
