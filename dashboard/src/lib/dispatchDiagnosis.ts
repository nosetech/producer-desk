import type { DispatchState } from "./types";

export type DiagTone = "working" | "idle" | "done" | "pending" | "warn";

export interface DiagMeta {
  label: string;
  tone: DiagTone;
  desc: string;
}

/** Claude Design ProducerDesk.dc.html の DIAG_META（issue #215）。 */
export const DIAG_META: Record<DispatchState, DiagMeta> = {
  running: {
    label: "実行中",
    tone: "working",
    desc: "エージェントがこのissueを処理しています。完了までお待ちください。",
  },
  queued: {
    label: "実行待ち",
    tone: "idle",
    desc: "実行キューに入っています。同じプロジェクトの作業が終わり次第着手します。",
  },
  completed: {
    label: "完了",
    tone: "done",
    desc: "最新の指示は処理済みです。追加の作業は返信で指示してください。",
  },
  not_dispatched: {
    label: "未処理の指示あり",
    tone: "pending",
    desc: "処理されていない指示コメントがあります。オーケストレータの停止などで取りこぼした可能性があります。",
  },
  orphaned_in_progress: {
    label: "in-progressだが実行されていない",
    tone: "warn",
    desc: "in-progress ラベルが付いていますが、実行中のエージェントがありません。",
  },
  not_managed: {
    label: "管理対象外",
    tone: "idle",
    desc: "Producer Desk のラベルが付いていないため、オーケストレータの管理対象外です。",
  },
};

/** 診断UIの配色トークン。`--working`等はClaude Design側の名称で、実装側のトークンに対応付ける。 */
export const TONE_VARS: Record<DiagTone, { color: string; bg: string }> = {
  working: { color: "--accent-blue", bg: "--accent-blue-bg" },
  idle: { color: "--accent-gray", bg: "--accent-gray-bg" },
  done: { color: "--accent-green", bg: "--accent-green-bg" },
  pending: { color: "--accent-amber", bg: "--accent-amber-bg" },
  warn: { color: "--warn", bg: "--warn-bg" },
};
