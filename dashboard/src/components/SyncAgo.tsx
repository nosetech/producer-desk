"use client";

import { useEffect, useState } from "react";
import { useApp } from "./AppContext";
import { formatRelativeTime, formatSyncTitle } from "@/lib/time";

/**
 * オーケストレータが実際にGitHubから情報を取得した時刻を相対表記（「N分前」）で表示する
 * （issue #197）。取得時刻から都度算出するため、再取得が無くても一定間隔で再描画して
 * 時間経過に追従する。
 */
export default function SyncAgo({
  fetchedAt,
  className,
  loadingText,
}: {
  fetchedAt: string | null;
  className?: string;
  /** 指定すると相対表記の代わりに表示する（取得中の「取得中…」表示用）。 */
  loadingText?: string;
}) {
  const { settings } = useApp();
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(
      () => setTick((t) => t + 1),
      settings.syncTickIntervalMs,
    );
    return () => clearInterval(timer);
  }, [settings.syncTickIntervalMs]);

  if (!fetchedAt && !loadingText) return null;
  return (
    <span
      className={className}
      title={fetchedAt ? formatSyncTitle(fetchedAt) : undefined}
    >
      {loadingText ?? (fetchedAt && formatRelativeTime(fetchedAt))}
    </span>
  );
}
