"use client";

import { useCallback, useEffect, useState } from "react";
import {
  deleteSnippet,
  fetchSnippets,
  reorderSnippets,
  saveSnippet,
} from "@/lib/api";
import {
  MAX_SNIPPETS,
  MAX_SNIPPET_BODY_LENGTH,
  MAX_SNIPPET_TITLE_LENGTH,
  checkSnippetDraft,
  firstLine,
  moveItem,
} from "@/lib/snippets";
import type { Snippet } from "@/lib/types";
import { useApp } from "./AppContext";
import {
  AlertCircleIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronUpIcon,
  InfoIcon,
  PlusIcon,
  SnippetIcon,
  TrashIcon,
  WarningIcon,
} from "./Icons";
import styles from "./SnippetSettings.module.css";

/** 一覧上の定型文。`isNew`は未保存の新規追加の下書き行（保存して初めて登録される）。 */
type Item = Snippet & { isNew?: boolean };
type Draft = { title: string; body: string };

const NEW_PREFIX = "new-";

function errorMessage(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback;
}

/**
 * 返信欄の定型文の管理画面（issue #323、docs/basic-design.md 2-5）。
 * デザインは Artifacts の feature/issue-323-snippets（プロンプト設定画面と同じ2ペイン構成）。
 */
export default function SnippetSettings() {
  const { showToast } = useApp();
  const [items, setItems] = useState<Item[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 未保存の編集内容（id → 下書き）。保存済みと同じになったら破棄する。
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [writeErr, setWriteErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  // モバイル幅では一覧と編集画面を切り替えて表示する（PC幅では常に2ペイン）。
  const [mobileEdit, setMobileEdit] = useState(false);

  const load = useCallback(async () => {
    try {
      const { snippets } = await fetchSnippets();
      setItems(snippets);
      setLoadError(null);
      setSelectedId((id) => id ?? snippets[0]?.id ?? null);
    } catch (e) {
      setLoadError(errorMessage(e, "定型文を取得できませんでした"));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!confirmDelete) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setConfirmDelete(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmDelete]);

  const list = items ?? [];
  const saved = list.filter((s) => !s.isNew);
  const current = list.find((s) => s.id === selectedId) ?? null;
  const draftOf = (s: Item): Draft =>
    drafts[s.id] ?? { title: s.title, body: s.body };
  const isDirty = (s: Item) => {
    const d = draftOf(s);
    return !!s.isNew || d.title !== s.title || d.body !== s.body;
  };

  function dropDraft(id: string) {
    setDrafts((d) => {
      const next = { ...d };
      delete next[id];
      return next;
    });
  }

  function select(id: string) {
    setSelectedId(id);
    setWriteErr(null);
    setMobileEdit(true);
    window.scrollTo({ top: 0 });
  }

  function setDraft(s: Item, patch: Partial<Draft>) {
    setWriteErr(null);
    setDrafts((d) => {
      const next = { ...d, [s.id]: { ...draftOf(s), ...patch } };
      if (
        !s.isNew &&
        next[s.id].title === s.title &&
        next[s.id].body === s.body
      )
        delete next[s.id];
      return next;
    });
  }

  function addNew() {
    if (saved.length >= MAX_SNIPPETS) return;
    const existing = list.find((s) => s.isNew);
    if (existing) return select(existing.id);
    const id = `${NEW_PREFIX}${Date.now()}`;
    setItems([...list, { id, title: "", body: "", isNew: true }]);
    select(id);
  }

  function discard(s: Item) {
    setWriteErr(null);
    dropDraft(s.id);
    if (!s.isNew) return;
    const rest = list.filter((x) => x.id !== s.id);
    setItems(rest);
    setSelectedId(rest.length ? rest[rest.length - 1].id : null);
    setMobileEdit(false);
  }

  async function save(s: Item) {
    const d = draftOf(s);
    if (!checkSnippetDraft(d.title, d.body).ok) return;
    setBusy(true);
    try {
      const result = await saveSnippet(
        { title: d.title, body: d.body },
        s.isNew ? undefined : s.id,
      );
      setItems((prev) => (prev ?? []).map((x) => (x.id === s.id ? result : x)));
      dropDraft(s.id);
      setSelectedId(result.id);
      setWriteErr(null);
      showToast("保存しました");
    } catch (e) {
      const message = errorMessage(e, "保存に失敗しました");
      setWriteErr(`${message}。変更内容はこの画面に残っています。`);
      showToast("定型文を保存できませんでした", true);
    } finally {
      setBusy(false);
    }
  }

  async function move(index: number, delta: number) {
    const next = moveItem(list, index, delta);
    if (next === list) return;
    setBusy(true);
    try {
      const { snippets } = await reorderSnippets(
        next.filter((s) => !s.isNew).map((s) => s.id),
      );
      setItems([...snippets, ...list.filter((s) => s.isNew)]);
    } catch (e) {
      showToast(
        `並び順を保存できませんでした（${errorMessage(e, "通信エラー")}）`,
        true,
      );
    } finally {
      setBusy(false);
    }
  }

  async function remove(s: Item) {
    const index = list.findIndex((x) => x.id === s.id);
    setBusy(true);
    try {
      const { snippets } = await deleteSnippet(s.id);
      const rest: Item[] = [...snippets, ...list.filter((x) => x.isNew)];
      setItems(rest);
      dropDraft(s.id);
      setSelectedId(rest[Math.min(index, rest.length - 1)]?.id ?? null);
      setMobileEdit(false);
      showToast("定型文を削除しました");
    } catch (e) {
      showToast(
        `定型文を削除できませんでした（${errorMessage(e, "通信エラー")}）`,
        true,
      );
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  const atMax = saved.length >= MAX_SNIPPETS;

  return (
    <div
      className={`${styles.page} ${mobileEdit ? styles.viewEdit : styles.viewList}`}
    >
      <div role="note" className={styles.notice}>
        <span className={styles.noticeIcon}>
          <InfoIcon size={16} />
        </span>
        <span className={styles.noticeText}>
          登録した定型文は、返信欄の『定型文』から選んでカーソル位置に挿入できます。全プロジェクト共通です。
        </span>
      </div>
      {loadError && (
        <div role="alert" className={styles.loadError}>
          定型文を取得できませんでした: {loadError}
        </div>
      )}
      {items && (
        <div className={styles.grid}>
          <section aria-label="定型文の一覧" className={styles.list}>
            <div className={styles.listHead}>
              <span className={styles.listHeadLabel}>
                定型文 · {saved.length} / {MAX_SNIPPETS}件
              </span>
              <AddButton
                disabled={atMax}
                title={
                  atMax
                    ? `上限の${MAX_SNIPPETS}件に達しています`
                    : "定型文を追加"
                }
                onClick={addNew}
              />
            </div>
            {list.length === 0 ? (
              <div className={styles.empty}>
                <div className={styles.emptyIcon}>
                  <SnippetIcon size={24} />
                </div>
                <div>
                  <div className={styles.emptyTitle}>
                    定型文はまだありません
                  </div>
                  <div className={styles.emptyDesc}>
                    「この方針で進めて」のような、返信でよく使う指示を登録しておけます。
                  </div>
                </div>
                <AddButton disabled={false} onClick={addNew} />
              </div>
            ) : (
              <div
                role="list"
                aria-label="定型文（この順で返信欄に表示されます）"
              >
                {list.map((s, i) => {
                  const d = draftOf(s);
                  const dirty = isDirty(s);
                  const invalid =
                    dirty && !checkSnippetDraft(d.title, d.body).ok;
                  const active = s.id === selectedId;
                  const label = d.title || "新しい定型文";
                  // 新規の下書き行は常に末尾に置き、保存済みの行と入れ替えない。
                  const upOff = i === 0 || busy || !!s.isNew;
                  const downOff =
                    i === list.length - 1 || busy || !!list[i + 1]?.isNew;
                  return (
                    <div
                      key={s.id}
                      role="listitem"
                      className={`${styles.row} ${active ? styles.rowActive : ""}`}
                    >
                      <button
                        type="button"
                        className={styles.rowBtn}
                        aria-current={active ? "true" : "false"}
                        onClick={() => select(s.id)}
                      >
                        <span className={styles.rowLine}>
                          <span className={styles.rowOrder}>{i + 1}</span>
                          <span className={styles.rowTitle}>
                            {d.title.trim() ||
                              (s.isNew ? "新しい定型文" : "（タイトルなし）")}
                          </span>
                          {invalid && (
                            <span
                              className={styles.invalidIcon}
                              title="未保存の変更に入力エラーがあります"
                            >
                              <AlertCircleIcon size={13} />
                            </span>
                          )}
                          {dirty && !invalid && (
                            <span
                              className={styles.unsavedDot}
                              title="未保存の変更があります"
                            />
                          )}
                        </span>
                        <span className={styles.rowFirst}>
                          {firstLine(d.body) || "本文なし"}
                        </span>
                      </button>
                      <button
                        type="button"
                        className={styles.moveBtn}
                        disabled={upOff}
                        aria-label={`「${label}」を上へ移動`}
                        title="上へ"
                        onClick={() => void move(i, -1)}
                      >
                        <ChevronUpIcon size={13} />
                      </button>
                      <button
                        type="button"
                        className={styles.moveBtn}
                        disabled={downOff}
                        aria-label={`「${label}」を下へ移動`}
                        title="下へ"
                        onClick={() => void move(i, 1)}
                      >
                        <ChevronDownIcon size={13} />
                      </button>
                      <span className={styles.rowChevron}>
                        <ChevronRightIcon size={15} />
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
          {current ? (
            <Editor
              key={current.id}
              item={current}
              draft={draftOf(current)}
              dirty={isDirty(current)}
              order={list.findIndex((x) => x.id === current.id) + 1}
              busy={busy}
              writeErr={writeErr}
              onBack={() => {
                setMobileEdit(false);
                window.scrollTo({ top: 0 });
              }}
              onChange={(patch) => setDraft(current, patch)}
              onDiscard={() => discard(current)}
              onSave={() => void save(current)}
              onAskDelete={() => setConfirmDelete(true)}
            />
          ) : (
            <div className={styles.pick}>
              定型文を選ぶか、新規追加してください
            </div>
          )}
        </div>
      )}
      {confirmDelete && current && !current.isNew && (
        <DeleteDialog
          item={current}
          busy={busy}
          onCancel={() => setConfirmDelete(false)}
          onConfirm={() => void remove(current)}
        />
      )}
    </div>
  );
}

function AddButton({
  disabled,
  title,
  onClick,
}: {
  disabled: boolean;
  title?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={styles.addBtn}
      disabled={disabled}
      title={title}
      onClick={onClick}
    >
      <PlusIcon size={13} strokeWidth={2.4} />
      新規追加
    </button>
  );
}

interface EditorProps {
  item: Item;
  draft: Draft;
  dirty: boolean;
  order: number;
  busy: boolean;
  writeErr: string | null;
  onBack: () => void;
  onChange: (patch: Partial<Draft>) => void;
  onDiscard: () => void;
  onSave: () => void;
  onAskDelete: () => void;
}

function Editor({
  item,
  draft,
  dirty,
  order,
  busy,
  writeErr,
  onBack,
  onChange,
  onDiscard,
  onSave,
  onAskDelete,
}: EditorProps) {
  const check = checkSnippetDraft(draft.title, draft.body);
  // 入力エラーは変更があるときだけ表示する（保存済みの内容は常に有効）。
  const showErr = dirty && !check.ok;
  const titleErr = showErr ? check.titleError : null;
  const bodyErr = showErr ? check.bodyError : null;
  const canSave = dirty && check.ok && !busy;
  const errors = [titleErr, bodyErr].filter((m): m is string => !!m);

  return (
    <section aria-label="定型文の編集" className={styles.editor}>
      <button type="button" className={styles.backBtn} onClick={onBack}>
        <ChevronLeftIcon size={16} />
        定型文一覧
      </button>
      <div className={styles.editorHead}>
        <div className={styles.editorTitleRow}>
          <h2 className={styles.editorTitle}>
            {draft.title.trim() ||
              (item.isNew ? "新しい定型文" : "（タイトルなし）")}
          </h2>
          {dirty && (
            <span className={styles.unsavedTag}>
              <span className={styles.unsavedTagDot} />
              未保存
            </span>
          )}
        </div>
        <span className={styles.orderNote}>
          {item.isNew
            ? "保存すると、返信欄の選択肢の末尾に追加されます"
            : `返信欄の「定型文」で ${order} 番目に表示されます`}
        </span>
      </div>

      <div>
        <div className={styles.labelRow}>
          <label htmlFor="sn-title" className={styles.label}>
            タイトル
          </label>
          <span
            className={`${styles.counter} ${check.titleLength > MAX_SNIPPET_TITLE_LENGTH ? styles.counterOver : ""}`}
          >
            {check.titleLength} / {MAX_SNIPPET_TITLE_LENGTH}
          </span>
        </div>
        <input
          id="sn-title"
          value={draft.title}
          onChange={(e) => onChange({ title: e.target.value })}
          placeholder="例: この方針で進めて"
          aria-invalid={!!titleErr}
          aria-describedby="sn-title-err"
          className={`${styles.field} ${styles.titleInput} ${titleErr ? styles.fieldInvalid : ""}`}
        />
        {titleErr && (
          <div id="sn-title-err" className={styles.fieldErr}>
            <AlertCircleIcon size={13} />
            {titleErr}
          </div>
        )}
      </div>

      <div>
        <div className={styles.labelRow}>
          <label htmlFor="sn-body" className={styles.label}>
            本文
          </label>
          <span
            className={`${styles.counter} ${check.bodyLength > MAX_SNIPPET_BODY_LENGTH ? styles.counterOver : ""}`}
          >
            {check.bodyLength.toLocaleString()} /{" "}
            {MAX_SNIPPET_BODY_LENGTH.toLocaleString()}
          </span>
        </div>
        <textarea
          id="sn-body"
          value={draft.body}
          onChange={(e) => onChange({ body: e.target.value })}
          placeholder="返信欄に挿入される文章です（固定文。プレースホルダは使えません）"
          aria-invalid={!!bodyErr}
          aria-describedby="sn-body-err"
          className={`${styles.field} ${styles.bodyInput} ${bodyErr ? styles.fieldInvalid : ""}`}
        />
        {bodyErr && (
          <div id="sn-body-err" className={styles.fieldErr}>
            <AlertCircleIcon size={13} />
            {bodyErr}
          </div>
        )}
      </div>

      {errors.length > 0 && (
        <div role="alert" className={styles.alert}>
          <span className={styles.alertIcon}>
            <WarningIcon size={16} />
          </span>
          <div className={styles.alertBody}>
            {errors.map((m) => (
              <div key={m} className={styles.alertLine}>
                <strong>保存できません:</strong> {m}
              </div>
            ))}
          </div>
        </div>
      )}
      {writeErr && (
        <div role="alert" className={styles.alert}>
          <span className={styles.alertIcon}>
            <WarningIcon size={16} />
          </span>
          <div className={styles.alertLine}>
            <strong>保存できませんでした:</strong> {writeErr}
          </div>
        </div>
      )}
      {dirty && check.ok && !writeErr && (
        <div className={styles.okLine}>
          <CheckIcon size={15} strokeWidth={2.6} />
          問題ありません — 保存できます
        </div>
      )}

      <div className={styles.foot}>
        {!item.isNew && (
          <button
            type="button"
            className={styles.deleteBtn}
            disabled={busy}
            onClick={onAskDelete}
          >
            <TrashIcon size={15} />
            削除
          </button>
        )}
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
          title={
            dirty && !check.ok
              ? "入力エラーを解消すると保存できます"
              : !dirty
                ? "変更はありません"
                : "保存する"
          }
          onClick={onSave}
        >
          <CheckIcon size={15} strokeWidth={2.6} />
          保存
        </button>
      </div>
    </section>
  );
}

function DeleteDialog({
  item,
  busy,
  onCancel,
  onConfirm,
}: {
  item: Item;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="sn-del-title"
        aria-describedby="sn-del-desc"
        className={styles.dialog}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.dialogHead}>
          <span className={styles.dialogIcon}>
            <TrashIcon size={18} />
          </span>
          <div id="sn-del-title" className={styles.dialogTitle}>
            定型文を削除しますか？
          </div>
        </div>
        <div className={styles.dialogTarget}>
          <div className={styles.dialogTargetTitle}>{item.title}</div>
          <div className={styles.dialogTargetBody}>{firstLine(item.body)}</div>
        </div>
        <div id="sn-del-desc" className={styles.dialogDesc}>
          返信欄の『定型文』の選択肢からも消えます。
          <strong>この操作は元に戻せません。</strong>
        </div>
        <div className={styles.dialogActions}>
          <button type="button" className={styles.cancelBtn} onClick={onCancel}>
            キャンセル
          </button>
          <button
            type="button"
            className={styles.confirmBtn}
            disabled={busy}
            onClick={onConfirm}
          >
            <TrashIcon size={15} />
            削除する
          </button>
        </div>
      </div>
    </div>
  );
}
