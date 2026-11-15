"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPlanJobs, type PlanJob } from "./api";
import { hasActivePlan } from "./planFlow";

// AI計画ジョブ（issue #299）の取得。実行中（キュー待ち・作成中）のジョブがある間は短い
// 間隔で、無いときは長い間隔でポーリングする（既存のポーリング統一方針）。
const ACTIVE_INTERVAL_MS = 3_000;
const IDLE_INTERVAL_MS = 20_000;

/**
 * プロジェクトの計画ジョブ一覧をポーリングする。
 * `onFinished`は、実行中だったジョブが完了（確認待ち・失敗）になったときに呼ぶ。
 */
export function usePlanJobs(
  repo: string,
  options: {
    enabled?: boolean;
    onFinished?: (job: PlanJob) => void;
  } = {},
): { jobs: PlanJob[]; loaded: boolean; refresh: () => Promise<void> } {
  const { enabled = true, onFinished } = options;
  const [jobs, setJobs] = useState<PlanJob[]>([]);
  const [loaded, setLoaded] = useState(false);
  const prevStatus = useRef<Map<string, string>>(new Map());
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(false);

  const load = useCallback(async (): Promise<PlanJob[] | null> => {
    if (!repo) return null;
    try {
      const { jobs: next } = await fetchPlanJobs(repo);
      if (!alive.current) return null;
      for (const job of next) {
        const before = prevStatus.current.get(job.id);
        if (
          (before === "queued" || before === "running") &&
          (job.status === "succeeded" || job.status === "failed")
        )
          onFinishedRef.current?.(job);
      }
      prevStatus.current = new Map(next.map((j) => [j.id, j.status]));
      setJobs(next);
      setLoaded(true);
      return next;
    } catch {
      // 取得失敗は次回のポーリングで復旧する。
      return null;
    }
  }, [repo]);

  const schedule = useCallback(
    (latest: PlanJob[] | null) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(
        async () => {
          const next = await load();
          if (alive.current) schedule(next ?? latest);
        },
        latest && hasActivePlan(latest) ? ACTIVE_INTERVAL_MS : IDLE_INTERVAL_MS,
      );
    },
    [load],
  );

  useEffect(() => {
    alive.current = true;
    prevStatus.current = new Map();
    setJobs([]);
    setLoaded(false);
    if (!enabled || !repo) return;
    void load().then((next) => {
      if (alive.current) schedule(next);
    });
    return () => {
      alive.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [enabled, repo, load, schedule]);

  /** 操作直後に呼ぶ。即時に再取得し、ポーリング間隔も組み直す。 */
  const refresh = useCallback(async () => {
    const next = await load();
    if (alive.current) schedule(next);
  }, [load, schedule]);

  return { jobs, loaded, refresh };
}
