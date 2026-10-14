"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchProgress } from "./api";
import {
  canStartJob,
  failureMessage,
  issueKey,
  removeJob,
  updateJob,
  type Job,
  type JobKind,
} from "./jobs";
import { randomProgressId, type StageDef } from "./stageProgress";

const POLL_INTERVAL_MS = 250;

export interface JobSpec {
  kind: JobKind;
  repo: string;
  /** 新規作成ではundefined。 */
  number?: number;
  title: string;
  stages: StageDef[];
  /** 実際の処理。progressIdはサーバのon_stage進捗ポーリングに使う。 */
  exec: (progressId: string) => Promise<unknown>;
  successMessage: string;
  /** trueを返すとジョブを失敗扱いにせず静かに破棄する（呼び出し側で別途処理済み）。 */
  onFailure?: (e: unknown) => boolean;
}

let newJobSeq = 0;

/**
 * 承認・マージ・返信・新規作成を、パネルやダイアログを塞がずバックグラウンドで実行する
 * （issue #212）。ジョブはissue単位で独立しており、別プロジェクトの操作を妨げない。
 */
export function useJobs({
  showToast,
  onSettled,
}: {
  showToast: (text: string, isError?: boolean) => void;
  onSettled: () => Promise<void>;
}) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const jobsRef = useRef<Job[]>([]);
  const specs = useRef(new Map<string, JobSpec>());

  const commit = useCallback((next: Job[]) => {
    jobsRef.current = next;
    setJobs(next);
  }, []);

  const run = useCallback(
    (key: string) => {
      const spec = specs.current.get(key);
      if (!spec) return;
      const progressId = randomProgressId();
      commit(
        updateJob(jobsRef.current, key, {
          status: "running",
          errorMessage: undefined,
          polledStage: null,
          progressId,
        }),
      );
      spec
        .exec(progressId)
        .then(() => {
          specs.current.delete(key);
          commit(removeJob(jobsRef.current, key));
          showToast(spec.successMessage);
          return onSettled();
        })
        .catch((e) => {
          if (spec.onFailure?.(e)) {
            specs.current.delete(key);
            commit(removeJob(jobsRef.current, key));
            return;
          }
          const job = jobsRef.current.find((j) => j.key === key);
          commit(
            updateJob(jobsRef.current, key, {
              status: "error",
              errorMessage: e instanceof Error ? e.message : undefined,
            }),
          );
          showToast(failureMessage(job ?? spec), true);
        });
    },
    [commit, showToast, onSettled],
  );

  /** 同一issueに実行中・失敗中の操作がある場合は開始せずfalseを返す。 */
  const startJob = useCallback(
    (spec: JobSpec): boolean => {
      if (!canStartJob(jobsRef.current, spec.repo, spec.number)) return false;
      const key =
        spec.number !== undefined
          ? issueKey(spec.repo, spec.number)
          : `new:${spec.repo}:${++newJobSeq}`;
      specs.current.set(key, spec);
      commit([
        ...jobsRef.current,
        {
          key,
          kind: spec.kind,
          repo: spec.repo,
          number: spec.number,
          title: spec.title,
          stages: spec.stages,
          status: "running",
          polledStage: null,
          progressId: "",
        },
      ]);
      run(key);
      return true;
    },
    [commit, run],
  );

  const retryJob = useCallback(
    (key: string) => {
      if (jobsRef.current.find((j) => j.key === key)?.status === "error")
        run(key);
    },
    [run],
  );

  const dismissJob = useCallback(
    (key: string) => {
      specs.current.delete(key);
      commit(removeJob(jobsRef.current, key));
    },
    [commit],
  );

  // 実行中ジョブの段階進捗をジョブごとに独立してポーリングする。
  const hasRunning = jobs.some((j) => j.status === "running");
  useEffect(() => {
    if (!hasRunning) return;
    const timer = setInterval(() => {
      for (const j of jobsRef.current) {
        if (j.status !== "running" || !j.progressId) continue;
        const { key, progressId } = j;
        fetchProgress(progressId)
          .then((res) => {
            const cur = jobsRef.current.find((x) => x.key === key);
            if (cur?.status === "running" && cur.progressId === progressId)
              commit(
                updateJob(jobsRef.current, key, { polledStage: res.stage }),
              );
          })
          .catch(() => {});
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hasRunning, commit]);

  return { jobs, startJob, retryJob, dismissJob };
}
