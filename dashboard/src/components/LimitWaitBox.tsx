"use client";

import { useEffect, useState } from "react";
import {
  fetchProjectSettings,
  postCancelLimitWait,
  postInstruct,
} from "@/lib/api";
import {
  formatResetAt,
  formatTimeLeft,
  limitResumeMessage,
} from "@/lib/limitWait";
import type { StageDef } from "@/lib/stageProgress";
import type { IssueSummary, LimitWaitInfo } from "@/lib/types";
import { useApp } from "./AppContext";
import cardStyles from "./DecisionCard.module.css";
import styles from "./LimitWaitBox.module.css";

// orchestrator/orchestrator/instruct.py の handle_instruct / handle_cancel_limit_wait の on_stage と対応する。
function resumeStages(alias: string): StageDef[] {
  return [
    {
      key: "comment",
      label: "コメントを投稿",
      note: `/model litellm:${alias}`,
    },
    { key: "label", label: "ラベルを更新", note: "label" },
    { key: "dispatch", label: "エージェントへ引き渡し", note: "queue" },
  ];
}
const CANCEL_STAGES: StageDef[] = [
  { key: "comment", label: "取り消しコメントを投稿", note: "POST comment" },
];

function ClockIcon({ size = 15, slash = false }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={size > 15 ? "2.2" : "2.3"}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ display: "block" }}
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
      {slash && <path d="m4 4 16 16" />}
    </svg>
  );
}

function SwitchIcon({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flex: "none" }}
    >
      <path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5" />
    </svg>
  );
}

function InfoIcon({ stroke = "currentColor" }: { stroke?: string }) {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke={stroke}
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={styles.noteIcon}
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 16v-5M12 8v.01" />
    </svg>
  );
}

/** 残り時間表示を30秒ごとに更新するための現在時刻。 */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30 * 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

/**
 * 判断待ちカードの「利用リミット待ち」ブロック（issue #331）。自動再開予定時刻・残り時間と、
 * 「別モデルで今すぐ再開」「自動再開を取り消す」の操作を表示する。
 */
export default function LimitWaitBox({
  decision,
  limitWait,
  busy,
}: {
  decision: IssueSummary;
  limitWait: LimitWaitInfo;
  busy: boolean;
}) {
  const { startJob } = useApp();
  const now = useNow();
  // undefined: 取得中。取得に失敗した場合も選べるモデル無しとして扱う。
  const [aliases, setAliases] = useState<string[] | undefined>(undefined);
  const [pickOpen, setPickOpen] = useState(false);
  const [pick, setPick] = useState<string | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchProjectSettings(decision.repo)
      .then((s) => alive && setAliases(s.available_models))
      .catch(() => alive && setAliases([]));
    return () => {
      alive = false;
    };
  }, [decision.repo]);

  const resetMs = Date.parse(limitWait.reset_at);
  const due = now >= resetMs;
  const at = formatResetAt(resetMs);
  const left = formatTimeLeft(resetMs - now);
  const noModel = aliases !== undefined && aliases.length === 0;
  const pickOff = busy || aliases === undefined || noModel;
  const repoName = decision.repo.split("/")[1];
  const label = `${repoName} #${decision.number}`;

  function openPick() {
    if (pickOff) return;
    setPick(null);
    setPickOpen(true);
  }

  function confirmPick() {
    if (!pick) return;
    const alias = pick;
    setPickOpen(false);
    startJob({
      kind: "limitResume",
      repo: decision.repo,
      number: decision.number,
      title: decision.title,
      stages: resumeStages(alias),
      runningHeading: `LiteLLM · ${alias} で再開中`,
      exec: (progressId) =>
        postInstruct(
          decision.repo,
          decision.number,
          "instruct",
          limitResumeMessage(alias),
          progressId,
        ),
      successMessage: `${label} を LiteLLM · ${alias} で再開しました。`,
    });
  }

  function confirmCancel() {
    setCancelOpen(false);
    startJob({
      kind: "limitCancel",
      repo: decision.repo,
      number: decision.number,
      title: decision.title,
      stages: CANCEL_STAGES,
      exec: (progressId) =>
        postCancelLimitWait(decision.repo, decision.number, progressId),
      successMessage: `${label} の自動再開を取り消しました。返信で再開の指示を出してください。`,
    });
  }

  const title = due ? "まもなく自動再開します" : "利用リミット待ち";
  const pickTitle =
    aliases === undefined
      ? "LiteLLM Proxy のモデルを確認しています"
      : noModel
        ? "LiteLLM Proxy のモデルが設定されていないため選べません"
        : "解除を待たずに、LiteLLM のモデルで今すぐ再開します";

  return (
    <>
      <section
        role="status"
        aria-label={due ? title : `利用リミット待ち。自動再開 ${at}、${left}`}
        className={styles.box}
      >
        <div className={styles.head}>
          <span className={styles.icon}>
            <span className={due ? styles.iconDue : undefined}>
              <ClockIcon />
            </span>
          </span>
          <div className={styles.headText}>
            <span className={styles.title}>{title}</span>
            <span className={styles.sub}>
              {due
                ? "リミットの解除時刻を過ぎました。オーケストレータの再開を待っています"
                : "Claude Code の利用リミットに達したため停止中です"}
            </span>
          </div>
          {!due && (
            <span className={`${styles.left} ${styles.leftHead}`}>{left}</span>
          )}
        </div>
        <div className={styles.meta}>
          <span className={styles.metaHead}>
            {due ? "解除予定" : "自動再開"}
          </span>
          <span className={styles.at}>{at}</span>
          <span>{due ? "（過ぎました）" : "· 同じセッションで再開"}</span>
          {!due && (
            <span className={`${styles.left} ${styles.leftMeta}`}>{left}</span>
          )}
        </div>
        <div className={styles.acts}>
          <button
            type="button"
            className={styles.pickBtn}
            onClick={openPick}
            disabled={pickOff}
            aria-haspopup="dialog"
            title={pickTitle}
          >
            <SwitchIcon />
            別モデルで今すぐ再開
          </button>
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={() => !busy && setCancelOpen(true)}
            disabled={busy}
            aria-haspopup="dialog"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              style={{ flex: "none" }}
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
            自動再開を取り消す
          </button>
        </div>
        {noModel && (
          <div className={styles.note}>
            <InfoIcon />
            <span>
              LiteLLM Proxy
              のモデルが設定されていないため、別モデルでは再開できません。プロジェクト設定で
              LiteLLM Proxy のモデルを追加すると選べるようになります。
            </span>
          </div>
        )}
      </section>

      {pickOpen && (
        <div
          className={cardStyles.confirmOverlay}
          onClick={() => setPickOpen(false)}
        >
          <div
            className={`${cardStyles.confirmDialog} ${styles.dialogWide}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby={`lm-pick-${decision.repo}-${decision.number}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.dlgHeading}>
              <span className={styles.iconWrap}>
                <SwitchIcon size={18} />
              </span>
              <span
                id={`lm-pick-${decision.repo}-${decision.number}`}
                className={styles.dlgTitle}
              >
                別のモデルで今すぐ再開
              </span>
            </div>
            <p className={styles.dlgDetail}>
              <span className={styles.dlgDetailNumber}>{label}</span> —{" "}
              {decision.title}
            </p>
            <p className={styles.dlgLead}>
              利用リミットの解除を待たずに、LiteLLM Proxy
              のモデルで作業を再開します。自動再開の予約は取り消されます。
            </p>
            <div className={styles.section}>
              <span className={styles.sectionHead}>LITELLM のモデル</span>
              <div
                role="radiogroup"
                aria-label="再開に使うモデル"
                className={styles.radioGroup}
              >
                {(aliases ?? []).map((alias) => {
                  const on = pick === alias;
                  return (
                    <div
                      key={alias}
                      role="radio"
                      tabIndex={0}
                      aria-checked={on}
                      className={`${styles.row} ${on ? styles.rowOn : ""}`}
                      onClick={() => setPick(alias)}
                      onKeyDown={(e) => {
                        if (
                          (e.key === "Enter" || e.key === " ") &&
                          e.target === e.currentTarget
                        ) {
                          e.preventDefault();
                          setPick(alias);
                        }
                      }}
                    >
                      <span className={styles.ring}>
                        <span className={styles.dot} />
                      </span>
                      <span className={styles.alias}>{alias}</span>
                      <span className={styles.aliasId}>litellm:{alias}</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div role="note" className={styles.dlgNote}>
              <InfoIcon stroke="var(--accent-amber)" />
              <span>
                選んだモデルは、
                <strong>このissueで以降も使われ続けます。</strong>
                Claude Code に戻すには、コメントで{" "}
                <code className={styles.code}>/model claude_code</code>{" "}
                と指示してください。
              </span>
            </div>
            <div className={styles.section}>
              <span className={styles.sectionHead}>投稿されるコメント</span>
              {pick ? (
                <pre className={styles.preview}>{limitResumeMessage(pick)}</pre>
              ) : (
                <div className={styles.previewEmpty}>
                  モデルを選ぶと、投稿されるコメントが表示されます
                </div>
              )}
            </div>
            <div className={styles.dlgActions}>
              <button
                type="button"
                className={styles.dlgCancelBtn}
                onClick={() => setPickOpen(false)}
              >
                キャンセル
              </button>
              <button
                type="button"
                className={styles.okBtn}
                onClick={confirmPick}
                disabled={!pick}
              >
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  style={{ flex: "none" }}
                >
                  <path d="m6 4 14 8-14 8V4Z" />
                </svg>
                このモデルで再開
              </button>
            </div>
          </div>
        </div>
      )}

      {cancelOpen && (
        <div
          className={cardStyles.confirmOverlay}
          onClick={() => setCancelOpen(false)}
        >
          <div
            className={`${cardStyles.confirmDialog} ${styles.dialogNarrow}`}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={`lm-cancel-${decision.repo}-${decision.number}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.dlgHeading}>
              <span className={styles.iconWrapPending}>
                <ClockIcon size={18} slash />
              </span>
              <span
                id={`lm-cancel-${decision.repo}-${decision.number}`}
                className={styles.dlgTitle}
              >
                自動再開を取り消しますか？
              </span>
            </div>
            <p className={styles.dlgDetail}>
              <span className={styles.dlgDetailNumber}>{label}</span> —{" "}
              {decision.title}
            </p>
            <p className={styles.dlgBody}>
              <span className={styles.dlgBodyAt}>{at}</span>{" "}
              の自動再開を取り消します。リミットが解除されても自動では再開しません。続きは返信で指示してください。
            </p>
            <div className={styles.dlgActions}>
              <button
                type="button"
                className={styles.dlgCancelBtn}
                onClick={() => setCancelOpen(false)}
              >
                キャンセル
              </button>
              <button
                type="button"
                className={styles.okPendingBtn}
                onClick={confirmCancel}
              >
                自動再開を取り消す
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
