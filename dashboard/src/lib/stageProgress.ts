"use client";

import { useEffect, useRef, useState } from "react";
import { fetchProgress } from "./api";

export interface StageDef {
  // orchestrator側のon_stageコールバックが通知する実際の完了ステップ名と対応する
  // キー。省略可能な段階（ブランチ削除・worktree同期等）が失敗/スキップされた場合、
  // サーバは `${key}_skipped` を返す。
  key: string;
  label: string;
  note: string;
}

export type StageRowState =
  "done" | "active" | "pending" | "skipped" | "failed";

export interface ResolvedStage extends StageDef {
  state: StageRowState;
}

const POLL_INTERVAL_MS = 250;
const SKIPPED_SUFFIX = "_skipped";

// `crypto.randomUUID()`はセキュアコンテキスト（HTTPS/localhost）でのみ使える。
// このダッシュボードは同一LAN内へのプレーンHTTPでの配布を前提としており
// （CLAUDE.md「確定済みの設計判断」）、LAN内の別端末からアクセスした場合は
// セキュアコンテキストにならないため使用しない。
export function randomProgressId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/**
 * ポーリングで得た最新の段階キーから、各行の表示状態を導出する。
 *
 * サーバ（ProgressStore）は「現在の最新段階」1つしか保持しないため、ポーリング間隔
 * より短時間で連続完了した段階は個別に観測できないことがある。必須段階については
 * インデックス比較（観測した段階より前は完了扱い）で吸収できるが、任意段階（スキップ
 * されうる段階）を観測し損ねた場合はスキップ表示にならず完了表示になる（狭い競合
 * 窓に限られる軽微な既知の制約）。
 */
export function resolveStages(
  defs: StageDef[],
  polledStage: string | null,
  status: "busy" | "success" | "error",
): ResolvedStage[] {
  const skipped = polledStage?.endsWith(SKIPPED_SUFFIX) ?? false;
  const baseKey = skipped
    ? polledStage!.slice(0, -SKIPPED_SUFFIX.length)
    : polledStage;
  const resolvedIdx = baseKey ? defs.findIndex((d) => d.key === baseKey) : -1;

  return defs.map((d, i) => {
    let state: StageRowState;
    if (i < resolvedIdx) {
      state = "done";
    } else if (i === resolvedIdx) {
      state = skipped ? "skipped" : status === "busy" ? "active" : "done";
    } else if (status === "error" && i === resolvedIdx + 1) {
      state = "failed";
    } else if (status === "busy" && i === resolvedIdx + 1) {
      state = "active";
    } else {
      state = "pending";
    }
    return { ...d, state };
  });
}

export function useStageProgress() {
  const [polledStage, setPolledStage] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  function stop() {
    if (pollTimer.current !== null) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }

  function start(): string {
    stop();
    const progressId = randomProgressId();
    setPolledStage(null);
    pollTimer.current = setInterval(() => {
      fetchProgress(progressId)
        .then((res) => setPolledStage(res.stage))
        .catch(() => {});
    }, POLL_INTERVAL_MS);
    return progressId;
  }

  function reset() {
    stop();
    setPolledStage(null);
  }

  useEffect(() => stop, []);

  return { polledStage, start, stop, reset };
}
