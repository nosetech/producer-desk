"use client";

import { useEffect, useState } from "react";
import { fetchProjectSettings, patchProjectSettings } from "@/lib/api";
import type { ExecutionMode } from "@/lib/types";
import { SpinnerIcon } from "./StageProgress";
import styles from "./ProjectSettingsDialog.module.css";

function GearIcon({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.1"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 8.9 19.3a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.7 8.9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.1A1.7 1.7 0 0 0 15 4.7a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9v.03a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1.03Z" />
    </svg>
  );
}

function CheckIcon({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function SaveIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" />
      <path d="M17 21v-8H7v8M7 3v5h8" />
    </svg>
  );
}

export default function ProjectSettingsDialog({
  repo,
  onClose,
  onSaved,
  onToast,
}: {
  repo: string;
  onClose: () => void;
  onSaved: () => void;
  onToast: (text: string) => void;
}) {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [runner, setRunner] = useState<ExecutionMode>("claude_code");
  const [model, setModel] = useState<string>("");
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const busy = loading || saving;
  const repoName = repo.split("/")[1] ?? repo;

  useEffect(() => {
    setLoading(true);
    setLoadError(null);
    setSaveError(null);
    setSaved(false);
    fetchProjectSettings(repo)
      .then((data) => {
        setRunner(data.execution_mode);
        setModel(data.litellm_model ?? data.available_models[0] ?? "");
        setAvailableModels(data.available_models);
      })
      .catch((e) => {
        setLoadError(
          e instanceof Error ? e.message : "設定の取得に失敗しました",
        );
      })
      .finally(() => setLoading(false));
  }, [repo]);

  function close() {
    if (saving) return;
    onClose();
  }

  function save() {
    if (busy) return;
    setSaving(true);
    setSaveError(null);
    patchProjectSettings(
      repo,
      runner,
      runner === "litellm_proxy" ? model : null,
    )
      .then(() => {
        setSaved(true);
        onToast(
          `${repoName} の実行手段を${
            runner === "litellm_proxy"
              ? `LiteLLM Proxy（${model}）`
              : "Claude Code"
          }に設定しました。`,
        );
        onSaved();
        setTimeout(onClose, 1200);
      })
      .catch((e) => {
        setSaveError(e instanceof Error ? e.message : "保存に失敗しました");
      })
      .finally(() => setSaving(false));
  }

  return (
    <div className={styles.overlay} onClick={close}>
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`settings-dialog-${repo}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.headingRow}>
          <span className={styles.iconBadge}>
            <GearIcon size={17} />
          </span>
          <div className={styles.headingText}>
            <div id={`settings-dialog-${repo}`} className={styles.title}>
              実行設定
            </div>
            <div className={styles.repoName}>{repo}</div>
          </div>
        </div>

        <p className={styles.description}>
          このプロジェクトの自走タスクを、どの実行手段で走らせるかの既定値です。
        </p>

        {loadError && (
          <div className={styles.errorBanner}>
            <span className={styles.errorHeading}>
              設定の取得に失敗しました
            </span>
            <span className={styles.errorDetail}>{loadError}</span>
          </div>
        )}

        <div className={styles.field}>
          <div className={styles.fieldLabel}>実行手段</div>
          <div className={styles.runnerRow}>
            <button
              type="button"
              className={`${styles.runnerBtn} ${runner === "claude_code" ? styles.runnerBtnActive : ""}`}
              onClick={() => setRunner("claude_code")}
              disabled={busy}
            >
              <div className={styles.runnerBtnHead}>
                {runner === "claude_code" && <CheckIcon size={14} />}
                <span>Claude Code</span>
              </div>
              <span className={styles.runnerBtnNote}>
                サブスクリプション内・追加コストなし
              </span>
            </button>
            <button
              type="button"
              className={`${styles.runnerBtn} ${runner === "litellm_proxy" ? styles.runnerBtnActive : ""}`}
              onClick={() => setRunner("litellm_proxy")}
              disabled={busy}
            >
              <div className={styles.runnerBtnHead}>
                {runner === "litellm_proxy" && <CheckIcon size={14} />}
                <span>LiteLLM Proxy経由</span>
              </div>
              <span className={styles.runnerBtnNote}>
                従量課金・他モデル／ローカルLLM
              </span>
            </button>
          </div>
        </div>

        {runner === "litellm_proxy" && (
          <div className={styles.field}>
            <div className={styles.fieldLabel}>使用するモデル</div>
            {availableModels.length > 0 ? (
              <select
                className={styles.select}
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={busy}
              >
                {availableModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            ) : (
              <div className={styles.noModelsHint}>
                config/litellm_config.yaml
                にこのプロジェクト向けのモデルが定義されていません。
              </div>
            )}
            <div className={styles.hint}>
              中継サーバー側の登録名です。利用量は「利用量・リミット」の従量枠に加算されます。
            </div>
          </div>
        )}

        {saveError && (
          <div className={styles.errorBanner}>
            <span className={styles.errorHeading}>保存できませんでした</span>
            <span className={styles.errorDetail}>{saveError}</span>
          </div>
        )}

        {saved && (
          <div className={styles.savedBanner}>
            <CheckIcon />
            <span>既定の実行設定を保存しました</span>
          </div>
        )}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={close}
            disabled={saving}
          >
            {saveError || saved ? "閉じる" : "キャンセル"}
          </button>
          <button
            type="button"
            className={styles.saveBtn}
            onClick={save}
            disabled={busy || saved || (runner === "litellm_proxy" && !model)}
          >
            {saving ? <SpinnerIcon trackOpacity={0.34} /> : <SaveIcon />}
            {saving
              ? "保存中…"
              : saveError
                ? "再試行"
                : saved
                  ? "保存しました"
                  : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
