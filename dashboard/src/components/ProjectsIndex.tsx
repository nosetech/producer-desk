"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useApp } from "./AppContext";
import styles from "./ProjectIssues.module.css";

/**
 * サイドバーの「issue一覧」の遷移先。直前に開いていた（なければ先頭の）プロジェクトの
 * issue一覧へ置き換えて遷移する。
 */
export default function ProjectsIndex() {
  const { repos } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (repos.length === 0) return;
    let last: string | null = null;
    try {
      last = localStorage.getItem("issueProject");
    } catch {}
    const target = last && repos.includes(last) ? last : repos[0];
    router.replace(`/projects/${target}`);
  }, [repos, router]);

  return (
    <div className={styles.page}>
      {repos.length === 0 && (
        <div className={styles.loadingHead}>プロジェクトを読み込み中…</div>
      )}
    </div>
  );
}
