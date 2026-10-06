"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { checkPrompt, diffLines } from "@/lib/promptEditor";
import type { PromptInfo } from "@/lib/types";
import { useApp } from "./AppContext";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  CheckIcon,
  CloseIcon,
  InfoIcon,
  PlusIcon,
  ResetIcon,
  ShieldIcon,
  WarningIcon,
} from "./Icons";
import styles from "./PromptSettings.module.css";

const PLACEHOLDER_DESCRIPTIONS: Record<string, string> = {
  repo: "リポジトリ名",
  issue_number: "issue番号",
};

/** Agent Runnerプロンプト設定画面（issue #149、docs/basic-design.md 3-6）。 */
export default function PromptSettings() {
  const { showToast } = useApp();
  const [prompts, setPrompts] = useState<PromptInfo[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  // 未保存の編集内容（キー → 本文）。保存済みの本文と同じになったら破棄する。
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [diffOn, setDiffOn] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [saving, setSaving] = useState(false);
  const [serverErrors, setServerErrors] = useState<string[]>([]);
  // モバイル幅では一覧と編集画面を切り替えて表示する（PC幅では常に2ペイン）。
  const [mobileEdit, setMobileEdit] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/prompts", { cache: "no-store" });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`);
      setPrompts(body.prompts as PromptInfo[]);
      setLoadError(null);
      setSelectedKey((k) => k ?? body.prompts[0]?.key ?? null);
    } catch (e) {
      setLoadError(
        e instanceof Error ? e.message : "プロンプトを取得できませんでした",
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const replacePrompt = (updated: PromptInfo) =>
    setPrompts((list) =>
      list ? list.map((p) => (p.key === updated.key ? updated : p)) : list,
    );

  const current = prompts?.find((p) => p.key === selectedKey) ?? null;
  const draftOf = (p: PromptInfo) => drafts[p.key] ?? p.text;

  function setDraft(p: PromptInfo, value: string) {
    setServerErrors([]);
    setDrafts((d) => {
      const next = { ...d };
      if (value === p.text) delete next[p.key];
      else next[p.key] = value;
      return next;
    });
  }

  function select(key: string) {
    setSelectedKey(key);
    setDiffOn(false);
    setServerErrors([]);
    setMobileEdit(true);
    window.scrollTo({ top: 0 });
  }

  function insertPlaceholder(p: PromptInfo, name: string) {
    const token = `{${name}}`;
    const ta = textareaRef.current;
    const text = draftOf(p);
    const start = ta?.selectionStart ?? text.length;
    const end = ta?.selectionEnd ?? text.length;
    setDraft(p, text.slice(0, start) + token + text.slice(end));
    requestAnimationFrame(() => {
      if (!ta) return;
      ta.focus();
      ta.setSelectionRange(start + token.length, start + token.length);
    });
  }

  async function save(p: PromptInfo) {
    setSaving(true);
    setServerErrors([]);
    try {
      const res = await fetch(`/api/prompts/${encodeURIComponent(p.key)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: draftOf(p) }),
      });
      const body = await res.json();
      if (!res.ok) {
        setServerErrors(
          Array.isArray(body.errors)
            ? body.errors
            : [body.error ?? "保存に失敗しました"],
        );
        return;
      }
      replacePrompt(body as PromptInfo);
      setDrafts((d) => {
        const next = { ...d };
        delete next[p.key];
        return next;
      });
      showToast("保存しました。次回のAgent Runner起動から反映されます");
    } catch (e) {
      setServerErrors([e instanceof Error ? e.message : "保存に失敗しました"]);
    } finally {
      setSaving(false);
    }
  }

  async function resetToDefault(p: PromptInfo) {
    setSaving(true);
    try {
      const res = await fetch(`/api/prompts/${encodeURIComponent(p.key)}`, {
        method: "DELETE",
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`);
      replacePrompt(body as PromptInfo);
      setDrafts((d) => {
        const next = { ...d };
        delete next[p.key];
        return next;
      });
      setDiffOn(false);
      showToast(`${p.key} をデフォルトに戻しました`);
    } catch (e) {
      showToast(
        e instanceof Error ? e.message : "デフォルトに戻せませんでした",
      );
    } finally {
      setSaving(false);
      setConfirmReset(false);
    }
  }

  const editedCount = prompts?.filter((p) => !p.is_default).length ?? 0;

  return (
    <div
      className={`${styles.page} ${mobileEdit ? styles.viewEdit : styles.viewList}`}
    >
      <div className={styles.head}>
        <h1 className={styles.title}>プロンプト設定</h1>
        <p className={styles.lead}>
          Agent Runner 起動時に渡す指示文（全{prompts?.length ?? "-"}
          種）を閲覧・編集します。
        </p>
      </div>
      <div role="note" className={styles.notice}>
        <span className={styles.noticeIcon}>
          <InfoIcon size={16} />
        </span>
        <span className={styles.noticeText}>
          変更は次回以降のAgent
          Runner起動分から反映されます。実行中のセッションには反映されません。
        </span>
      </div>
      {loadError && (
        <div role="alert" className={styles.loadError}>
          {loadError}
        </div>
      )}
      {prompts && (
        <div className={styles.grid}>
          <div className={styles.list}>
            <div className={styles.listHead}>
              <span className={styles.listHeadLabel}>
                指示文 · {prompts.length}
              </span>
              <span className={styles.listHeadCount}>
                {editedCount} 件 編集済み
              </span>
            </div>
            {prompts.map((p) => {
              const draft = draftOf(p);
              const unsaved = draft !== p.text;
              const invalid = unsaved && !checkPrompt(p, draft).ok;
              const n = p.required_tokens.length;
              return (
                <button
                  key={p.key}
                  type="button"
                  className={`${styles.row} ${p.key === selectedKey ? styles.rowActive : ""}`}
                  aria-current={p.key === selectedKey ? "true" : undefined}
                  onClick={() => select(p.key)}
                >
                  <span className={styles.rowLine}>
                    <span className={styles.rowName}>{p.title}</span>
                    {invalid && (
                      <span
                        className={styles.invalidIcon}
                        title="未保存の変更に検証エラーがあります"
                      >
                        <WarningIcon size={13} />
                      </span>
                    )}
                    {unsaved && !invalid && (
                      <span
                        className={styles.unsavedDot}
                        title="未保存の変更があります"
                      />
                    )}
                    <StateBadge edited={!p.is_default} />
                    <span className={styles.rowChevron}>
                      <ChevronRightIcon size={16} />
                    </span>
                  </span>
                  <span className={styles.rowLine}>
                    <span className={styles.rowKey}>{p.key}</span>
                    <span
                      className={`${styles.tokBadge} ${n ? "" : styles.tokBadgeNone}`}
                      title={
                        n ? `必須トークンあり（${n}）` : "必須トークンなし"
                      }
                    >
                      <ShieldIcon size={12} />
                      {n ? `必須 ${n}` : "なし"}
                    </span>
                  </span>
                  <span className={styles.rowPurpose}>{p.description}</span>
                </button>
              );
            })}
          </div>
          {current && (
            <Editor
              key={current.key}
              prompt={current}
              draft={draftOf(current)}
              diffOn={diffOn}
              saving={saving}
              serverErrors={serverErrors}
              textareaRef={textareaRef}
              onBack={() => {
                setMobileEdit(false);
                window.scrollTo({ top: 0 });
              }}
              onChange={(v) => setDraft(current, v)}
              onToggleDiff={() => setDiffOn((v) => !v)}
              onInsert={(name) => insertPlaceholder(current, name)}
              onDiscard={() => setDraft(current, current.text)}
              onSave={() => void save(current)}
              onAskReset={() => setConfirmReset(true)}
            />
          )}
        </div>
      )}
      {confirmReset && current && (
        <ResetDialog
          prompt={current}
          saving={saving}
          onCancel={() => setConfirmReset(false)}
          onConfirm={() => void resetToDefault(current)}
        />
      )}
    </div>
  );
}

function StateBadge({ edited }: { edited: boolean }) {
  return (
    <span className={`${styles.badge} ${edited ? styles.badgeEdited : ""}`}>
      {edited ? "編集済み" : "デフォルト"}
    </span>
  );
}

interface EditorProps {
  prompt: PromptInfo;
  draft: string;
  diffOn: boolean;
  saving: boolean;
  serverErrors: string[];
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onBack: () => void;
  onChange: (value: string) => void;
  onToggleDiff: () => void;
  onInsert: (name: string) => void;
  onDiscard: () => void;
  onSave: () => void;
  onAskReset: () => void;
}

function Editor({
  prompt,
  draft,
  diffOn,
  saving,
  serverErrors,
  textareaRef,
  onBack,
  onChange,
  onToggleDiff,
  onInsert,
  onDiscard,
  onSave,
  onAskReset,
}: EditorProps) {
  const check = checkPrompt(prompt, draft);
  const dirty = draft !== prompt.text;
  const canSave = dirty && check.ok && !saving;
  const anyMissing = check.missing.length > 0;
  const atDefault = prompt.is_default && draft === prompt.default;
  const diff = diffLines(prompt.default, draft);
  const errors = [
    ...(check.empty ? [{ tok: null, msg: "本文が空です" }] : []),
    ...check.missing.map((t) => ({ tok: t, msg: "が含まれていません" })),
    ...check.unknown.map((u) => ({
      tok: `{${u}}`,
      msg: "は使用できないプレースホルダです",
    })),
    ...serverErrors.map((m) => ({ tok: null, msg: m })),
  ];

  return (
    <div className={styles.editor}>
      <button type="button" className={styles.backBtn} onClick={onBack}>
        <ChevronLeftIcon size={18} />
        プロンプト一覧
      </button>
      <div className={styles.editorHead}>
        <div className={styles.editorTitleBlock}>
          <div className={styles.editorTitleRow}>
            <h2 className={styles.editorTitle}>{prompt.title}</h2>
            <StateBadge edited={!prompt.is_default} />
            {dirty && (
              <span className={styles.unsavedTag}>
                <span className={styles.unsavedTagDot} />
                未保存
              </span>
            )}
          </div>
          <span className={styles.editorKey}>{prompt.key}</span>
          <span className={styles.editorPurpose}>{prompt.description}</span>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={diffOn}
          className={`${styles.diffBtn} ${diffOn ? styles.diffBtnOn : ""}`}
          onClick={onToggleDiff}
        >
          <span className={styles.diffTrack}>
            <span className={styles.diffKnob} />
          </span>
          デフォルトとの差分
        </button>
      </div>

      {prompt.required_tokens.length > 0 ? (
        <section
          aria-label="必須トークン"
          className={`${styles.tokPanel} ${anyMissing ? styles.tokPanelWarn : ""}`}
        >
          <div className={styles.tokPanelHead}>
            <span className={styles.tokIcon}>
              <WarningIcon size={16} />
            </span>
            <div className={styles.tokPanelText}>
              <div className={styles.tokPanelTitle}>
                必須トークン — 削除すると自動処理が壊れます
              </div>
              <div className={styles.tokPanelDesc}>
                Agent Runner
                はこれらの文字列を機械的に検出しています。文章は書き換えても構いませんが、トークンは一字一句そのまま残してください。
              </div>
            </div>
          </div>
          <div className={styles.tokList}>
            {prompt.required_tokens.map((t) => {
              const missing = check.missing.includes(t.token);
              return (
                <div key={t.token} className={styles.tokRow}>
                  <span
                    className={`${styles.tokChip} ${missing ? styles.tokChipMissing : ""}`}
                  >
                    {missing ? (
                      <CloseIcon size={12} />
                    ) : (
                      <CheckIcon size={12} />
                    )}
                    <span className={styles.tokChipText}>{t.token}</span>
                  </span>
                  <span className={styles.tokWhy}>
                    {missing && (
                      <strong className={styles.tokMissingMark}>
                        含まれていません ·{" "}
                      </strong>
                    )}
                    {t.reason}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      ) : (
        <div className={styles.noTokens}>
          <ShieldIcon size={14} />
          必須トークンはありません
        </div>
      )}

      <div className={styles.phBox}>
        <div className={styles.phHead}>
          <span className={styles.phTitle}>プレースホルダ</span>
          <span className={styles.phHint}>クリックでカーソル位置に挿入</span>
        </div>
        <div className={styles.phChips}>
          {prompt.placeholders.map((name) => (
            <button
              key={name}
              type="button"
              className={styles.phChip}
              disabled={diffOn}
              title="カーソル位置に挿入"
              onClick={() => onInsert(name)}
            >
              <PlusIcon size={12} />
              {`{${name}}`}
              <span className={styles.phDesc}>
                {PLACEHOLDER_DESCRIPTIONS[name] ?? ""}
              </span>
            </button>
          ))}
          {check.unknown.map((u) => (
            <span key={u} className={styles.phUnknown}>
              <CloseIcon size={12} />
              {`{${u}}`}
              <span className={styles.phUnknownNote}>使用不可</span>
            </span>
          ))}
        </div>
        <div className={styles.phNote}>
          波括弧で囲んだ{" "}
          {prompt.placeholders.map((n, i) => (
            <span key={n}>
              {i > 0 && " / "}
              <code>{`{${n}}`}</code>
            </span>
          ))}{" "}
          は Agent Runner 起動時に実際の値へ置き換えられます。
          <strong>それ以外の波括弧変数は使用できません。</strong>
        </div>
      </div>

      {diffOn ? (
        <div className={styles.diffBox}>
          <div className={styles.diffLegend}>
            <span className={styles.diffLegendTitle}>
              デフォルト → 現在の内容
            </span>
            <span className={styles.diffLegendItem}>
              <span
                className={styles.diffLegendSwatch}
                style={{ background: "var(--warn)" }}
              />
              削除 {diff.filter((d) => d[0] === "-").length}行
            </span>
            <span className={styles.diffLegendItem}>
              <span
                className={styles.diffLegendSwatch}
                style={{ background: "var(--accent-green)" }}
              />
              追加 {diff.filter((d) => d[0] === "+").length}行
            </span>
            <span className={styles.diffLegendSpacer} />
            <span className={styles.diffLegendNote}>
              差分表示中は編集できません
            </span>
          </div>
          {draft === prompt.default && (
            <div className={styles.diffSame}>デフォルトと同じ内容です</div>
          )}
          <div className={styles.diffBody}>
            {diff.map(([sign, text], i) => (
              <div
                key={i}
                className={`${styles.diffLine} ${
                  sign === "+"
                    ? styles.diffAdd
                    : sign === "-"
                      ? styles.diffDel
                      : ""
                }`}
              >
                <span className={styles.diffSign}>
                  {sign === " " ? "" : sign}
                </span>
                <span className={styles.diffText}>{text || " "}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => onChange(e.target.value)}
          aria-label="指示文"
          spellCheck={false}
          className={`${styles.textarea} ${check.ok ? "" : styles.textareaInvalid}`}
        />
      )}

      {errors.length > 0 && (
        <div role="alert" className={styles.alert}>
          <span className={styles.alertIcon}>
            <WarningIcon size={16} />
          </span>
          <div className={styles.alertBody}>
            {errors.map((er, i) => (
              <div key={i} className={styles.alertLine}>
                <strong>保存できません:</strong>{" "}
                {er.tok && <code>{er.tok}</code>} {er.msg}
              </div>
            ))}
          </div>
        </div>
      )}
      {dirty && check.ok && errors.length === 0 && (
        <div className={styles.okLine}>
          <CheckIcon size={14} />
          {prompt.required_tokens.length
            ? "必須トークンはすべて含まれています · 保存できます"
            : "問題ありません · 保存できます"}
        </div>
      )}

      <div className={styles.foot}>
        <button
          type="button"
          className={styles.resetBtn}
          disabled={atDefault || saving}
          onClick={onAskReset}
        >
          <ResetIcon size={15} />
          デフォルトに戻す
        </button>
        <span className={styles.footSpacer} />
        <button
          type="button"
          className={styles.discardBtn}
          disabled={!dirty}
          onClick={onDiscard}
        >
          変更を破棄
        </button>
        <button
          type="button"
          className={styles.saveBtn}
          disabled={!canSave}
          onClick={onSave}
        >
          <CheckIcon size={14} />
          保存
        </button>
      </div>
    </div>
  );
}

function ResetDialog({
  prompt,
  saving,
  onCancel,
  onConfirm,
}: {
  prompt: PromptInfo;
  saving: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const diff = diffLines(prompt.default, prompt.text);
  const added = diff.filter((d) => d[0] === "+").length;
  const removed = diff.filter((d) => d[0] === "-").length;
  const summary = prompt.is_default ? "なし" : `+${added} / −${removed}行`;
  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div
        role="alertdialog"
        aria-label="デフォルトに戻す"
        className={styles.dialog}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.dialogHead}>
          <span className={styles.dialogIcon}>
            <ResetIcon size={18} />
          </span>
          <div className={styles.dialogTitle}>デフォルトに戻しますか？</div>
        </div>
        <div className={styles.dialogBody}>
          <span className={styles.dialogKey}>{prompt.key}</span>（{prompt.title}
          ）の指示文を初期状態に戻します。
        </div>
        <div className={styles.dialogWarn}>
          <span className={styles.dialogWarnIcon}>
            <WarningIcon size={16} />
          </span>
          <div className={styles.dialogWarnText}>
            <strong>
              保存済みの編集内容（{summary}）と未保存の変更は破棄されます。
            </strong>
            この操作は元に戻せません。次回以降の起動分からデフォルトの指示文が使われます。
          </div>
        </div>
        <div className={styles.dialogActions}>
          <button type="button" className={styles.cancelBtn} onClick={onCancel}>
            キャンセル
          </button>
          <button
            type="button"
            className={styles.confirmBtn}
            disabled={saving}
            onClick={onConfirm}
          >
            <ResetIcon size={15} />
            デフォルトに戻す
          </button>
        </div>
      </div>
    </div>
  );
}
