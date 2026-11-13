"use client";

import { useState } from "react";
import { deleteInbox, patchInbox, postInbox } from "@/lib/api";
import {
  DEFAULT_INBOX_KIND,
  INBOX_KINDS,
  INBOX_TITLE_MAX,
  canSubmitInbox,
  inboxKindMeta,
  sortInbox,
} from "@/lib/inbox";
import { formatAbsoluteTime } from "@/lib/issueList";
import type { InboxItem, InboxKind } from "@/lib/types";
import { useApp } from "./AppContext";
import { PlusIcon, WarningIcon } from "./Icons";
import styles from "./InboxSection.module.css";

// ProjectIssues.tsx（issue一覧画面）の上部に置くinboxセクション（issue #288）。
// デザイン: Artifactsの feature/issue-288-inbox（種別ごとの色・行レイアウト・状態表示）。

function Spinner({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 42 42"
      aria-hidden="true"
      className={styles.spin}
    >
      <circle
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        opacity="0.3"
      />
      <circle
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray="34 200"
      />
    </svg>
  );
}

function Icon({ d, size = 13 }: { d: string[]; size?: number }) {
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
      aria-hidden="true"
      style={{ flex: "none" }}
    >
      {d.map((p) => (
        <path key={p} d={p} />
      ))}
    </svg>
  );
}

const PATHS = {
  chevron: ["m9 18 6-6-6-6"],
  inbox: [
    "M22 12h-6l-2 3h-4l-2-3H2",
    "M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z",
  ],
  bug: [
    "m8 2 1.88 1.88M14.12 3.88 16 2M9 7.13v-1a3 3 0 1 1 6 0v1",
    "M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6",
    "M12 20v-9M6.53 9C4.6 8.8 3 7.1 3 5M6 13H2M3 21c0-2.1 1.7-3.9 3.8-4M20.97 5c0 2.1-1.6 3.8-3.5 4M22 13h-4M17.2 17c2.1.1 3.8 1.9 3.8 4",
  ],
  idea: [
    "M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5",
    "M9 18h6M10 22h4",
  ],
  other: [
    "M15.5 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8.5L15.5 3Z",
    "M15 3v6h6",
  ],
  sparkle: [
    "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9Z",
    "M19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7Z",
  ],
  edit: ["M12 20h9", "M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"],
  trash: [
    "M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6",
  ],
  minus: ["M5 12h14"],
};

function KindBadge({ kind }: { kind: InboxKind }) {
  const meta = inboxKindMeta(kind);
  const icon =
    kind === "bug"
      ? PATHS.bug
      : kind === "enhancement"
        ? PATHS.idea
        : PATHS.other;
  return (
    <span
      className={styles.badge}
      style={{
        background: `var(${meta.bgVar})`,
        color: `var(${meta.colorVar})`,
      }}
    >
      <Icon d={icon} size={12} />
      {meta.label}
    </span>
  );
}

function KindSelect({
  value,
  disabled,
  onChange,
  className,
}: {
  value: InboxKind;
  disabled: boolean;
  onChange: (kind: InboxKind) => void;
  className: string;
}) {
  return (
    <select
      className={className}
      value={value}
      required
      disabled={disabled}
      aria-label="種別（必須）"
      onChange={(e) => onChange(e.target.value as InboxKind)}
    >
      {INBOX_KINDS.map((k) => (
        <option key={k.kind} value={k.kind}>
          {k.label}
        </option>
      ))}
    </select>
  );
}

function ErrorBox({
  title,
  message,
  onRetry,
  backLabel,
  onBack,
}: {
  title: string;
  message: string;
  onRetry: () => void;
  backLabel: string;
  onBack: () => void;
}) {
  return (
    <div role="alert" className={styles.errBox}>
      <div className={styles.errHead}>
        <WarningIcon size={16} />
        <div className={styles.errText}>
          <span className={styles.errTitle}>{title}</span>
          <span className={styles.errMessage}>{message}</span>
        </div>
      </div>
      <div className={styles.errActions}>
        <button type="button" className={styles.errRetry} onClick={onRetry}>
          再試行
        </button>
        <button type="button" className={styles.errBack} onClick={onBack}>
          {backLabel}
        </button>
      </div>
    </div>
  );
}

type Phase = "idle" | "busy" | "error";

function InboxRowEditor({
  repo,
  item,
  onDone,
  onSaved,
}: {
  repo: string;
  item: InboxItem;
  onDone: () => void;
  onSaved: () => void;
}) {
  const [kind, setKind] = useState<InboxKind>(item.kind);
  const [title, setTitle] = useState(item.title);
  const [body, setBody] = useState(item.body);
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState("");
  const busy = phase === "busy";
  const canSave = canSubmitInbox({ kind, title, body }) && !busy;

  async function save() {
    if (!canSave) return;
    setPhase("busy");
    try {
      await patchInbox(repo, item.number, { kind, title: title.trim(), body });
      onSaved();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "不明なエラー");
      setPhase("error");
    }
  }

  return (
    <div
      role="group"
      aria-label={`#${item.number} を編集`}
      className={styles.editWrap}
    >
      <div className={styles.editHead}>
        <span className={styles.editLabel}>編集中</span>
        <span className={styles.num}>#{item.number}</span>
        <span style={{ flex: 1 }} />
        <time className={styles.date} dateTime={item.created_at}>
          {formatAbsoluteTime(item.created_at)}
        </time>
      </div>
      <div className={styles.editRow}>
        <KindSelect
          className={styles.select}
          value={kind}
          disabled={busy}
          onChange={setKind}
        />
        <input
          className={`${styles.input} ${styles.inputBold}`}
          value={title}
          maxLength={INBOX_TITLE_MAX}
          required
          disabled={busy}
          aria-label="一言メモ（必須）"
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <textarea
        className={styles.textarea}
        value={body}
        disabled={busy}
        aria-label="補足（任意）"
        placeholder="補足（任意）: 再現手順・背景・参考リンクなど"
        onChange={(e) => setBody(e.target.value)}
      />
      {phase === "error" && (
        <ErrorBox
          title="変更を保存できませんでした"
          message={`${message}。編集した内容はそのまま残っています。`}
          onRetry={save}
          backLabel="編集に戻る"
          onBack={() => setPhase("idle")}
        />
      )}
      <div className={styles.editFoot}>
        <button
          type="button"
          className={styles.primary}
          disabled={!canSave}
          aria-busy={busy}
          onClick={save}
        >
          {busy && <Spinner size={14} />}
          {busy ? "保存中…" : "保存"}
        </button>
        <button
          type="button"
          className={styles.ghost}
          disabled={busy}
          onClick={onDone}
        >
          キャンセル
        </button>
      </div>
    </div>
  );
}

function DeleteDialog({
  repo,
  item,
  onClose,
  onDeleted,
}: {
  repo: string;
  item: InboxItem;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState("");
  const busy = phase === "busy";

  async function confirm() {
    if (busy) return;
    setPhase("busy");
    try {
      await deleteInbox(repo, item.number);
      onDeleted();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "不明なエラー");
      setPhase("error");
    }
  }

  return (
    <>
      <div className={styles.backdrop} onClick={busy ? undefined : onClose} />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="ib-del-title"
        aria-describedby="ib-del-desc"
        className={styles.dialog}
      >
        <div className={styles.dialogHead}>
          <span className={styles.dialogIcon}>
            <Icon d={PATHS.trash} size={18} />
          </span>
          <div id="ib-del-title" className={styles.dialogTitle}>
            inboxから削除しますか？
          </div>
        </div>
        <div className={styles.dialogCard}>
          <div className={styles.dialogMeta}>
            <KindBadge kind={item.kind} />
            <span className={styles.dialogNum}>
              {repo} #{item.number}
            </span>
          </div>
          <div className={styles.dialogItemTitle}>{item.title}</div>
          {item.body && (
            <div className={styles.dialogItemBody}>{item.body}</div>
          )}
        </div>
        <div id="ib-del-desc" className={styles.dialogDesc}>
          GitHubのissue <span className={styles.dialogNum}>#{item.number}</span>{" "}
          を「not planned」でクローズし、inboxから外します。
          <strong>この画面からは元に戻せません。</strong>
        </div>
        {busy && (
          <div role="status" aria-live="polite" className={styles.dialogBusy}>
            <Spinner size={14} />
            issueをクローズしています…
          </div>
        )}
        {phase === "error" && (
          <div role="alert" className={styles.dialogErr}>
            <WarningIcon size={16} />
            <div>
              <strong>削除できませんでした。</strong>
              {message}。メモはinboxに残っています。
            </div>
          </div>
        )}
        <div className={styles.dialogFoot}>
          <button
            type="button"
            className={styles.ghost}
            disabled={busy}
            onClick={onClose}
          >
            キャンセル
          </button>
          <button
            type="button"
            className={styles.danger}
            disabled={busy}
            aria-busy={busy}
            onClick={confirm}
          >
            {busy ? <Spinner size={15} /> : <Icon d={PATHS.trash} size={15} />}
            {busy ? "削除中…" : phase === "error" ? "再試行" : "削除する"}
          </button>
        </div>
      </div>
    </>
  );
}

export default function InboxSection({
  repo,
  items,
  onChanged,
}: {
  repo: string;
  items: InboxItem[];
  /** 登録・編集・削除の成功後に、一覧を再取得させる。 */
  onChanged: () => void;
}) {
  const { openNewTask, showToast } = useApp();
  const [open, setOpen] = useState(true);
  const [kind, setKind] = useState<InboxKind>(DEFAULT_INBOX_KIND);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [bodyOpen, setBodyOpen] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<InboxItem | null>(null);
  const [newId, setNewId] = useState<number | null>(null);

  const sorted = sortInbox(items);
  const adding = phase === "busy";
  const canAdd = canSubmitInbox({ kind, title, body }) && !adding;

  async function add() {
    if (!canAdd) return;
    setPhase("busy");
    try {
      const res = await postInbox(repo, { kind, title: title.trim(), body });
      setTitle("");
      setBody("");
      setBodyOpen(false);
      setPhase("idle");
      setNewId(res.issue_number);
      showToast(
        `inboxに追加しました（#${res.issue_number}）。計画するまでAIは実行しません。`,
      );
      onChanged();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "不明なエラー");
      setPhase("error");
    }
  }

  return (
    <section aria-label="inbox（未計画のメモ）" className={styles.section}>
      <div className={styles.head}>
        <button
          type="button"
          className={styles.toggle}
          aria-expanded={open}
          aria-controls="inbox-body"
          title={open ? "inboxを折りたたむ" : "inboxを展開する"}
          onClick={() => setOpen((o) => !o)}
        >
          <span
            className={styles.chev}
            style={{ transform: open ? "rotate(90deg)" : "none" }}
          >
            <Icon d={PATHS.chevron} size={14} />
          </span>
          <span className={styles.headIcon}>
            <Icon d={PATHS.inbox} size={14} />
          </span>
          <span className={styles.headTitle}>inbox</span>
          <span className={styles.count}>
            <span className={styles.srOnly}>件数 </span>
            {sorted.length}
          </span>
        </button>
        <span className={styles.note}>
          <span className={styles.noteFull}>
            未計画のメモ ·
            「計画する」で計画し、承認するとissueに昇格します。AIは自動実行しません。
          </span>
          <span className={styles.noteShort}>
            未計画 · AIは自動実行しません
          </span>
        </span>
      </div>

      {open && (
        <div id="inbox-body" className={styles.body}>
          <div className={styles.form}>
            <div className={styles.formRow}>
              <KindSelect
                className={`${styles.select} ${styles.formKind}`}
                value={kind}
                disabled={adding}
                onChange={setKind}
              />
              <input
                className={`${styles.input} ${styles.formTitle} ${phase === "error" ? styles.inputError : ""}`}
                value={title}
                maxLength={INBOX_TITLE_MAX}
                required
                disabled={adding}
                aria-label="一言メモ（必須）"
                placeholder="一言メモ（例: 明細が多いとプレビューが遅い）"
                onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    !e.nativeEvent.isComposing &&
                    !e.shiftKey
                  ) {
                    e.preventDefault();
                    void add();
                  }
                }}
              />
              <button
                type="button"
                className={styles.bodyToggle}
                disabled={adding}
                aria-expanded={bodyOpen}
                aria-controls="inbox-note"
                onClick={() => setBodyOpen((o) => !o)}
              >
                {bodyOpen ? (
                  <Icon d={PATHS.minus} />
                ) : (
                  <PlusIcon size={13} strokeWidth={2.4} />
                )}
                {bodyOpen ? "補足を閉じる" : "補足を書く"}
                {!bodyOpen && body.trim() && (
                  <span className={styles.dot} title="補足が入力されています" />
                )}
              </button>
              <button
                type="button"
                className={styles.primary}
                disabled={!canAdd}
                aria-busy={adding}
                onClick={add}
              >
                {adding ? (
                  <Spinner size={14} />
                ) : (
                  <PlusIcon size={14} strokeWidth={2.4} />
                )}
                {adding ? "追加中…" : "追加"}
              </button>
            </div>
            {bodyOpen && (
              <div className={styles.noteBlock}>
                <textarea
                  id="inbox-note"
                  className={styles.textarea}
                  value={body}
                  disabled={adding}
                  aria-label="補足（任意）"
                  placeholder="補足（任意）: 再現手順・背景・参考リンクなど"
                  onChange={(e) => setBody(e.target.value)}
                />
                <span className={styles.hint}>
                  補足は任意です。「計画する」ときに一言メモと一緒にAIへ渡されます。
                </span>
              </div>
            )}
            {adding && (
              <span role="status" aria-live="polite" className={styles.hint}>
                {repo} に inbox のissueとして登録しています…
              </span>
            )}
            {phase === "error" && (
              <ErrorBox
                title="inboxに追加できませんでした"
                message={`${message}。入力した内容はそのまま残っています。`}
                onRetry={add}
                backLabel="閉じる"
                onBack={() => setPhase("idle")}
              />
            )}
          </div>

          {sorted.length === 0 ? (
            <div className={styles.empty}>
              <Icon d={PATHS.inbox} size={18} />
              <span>inboxは空です。思いついたことを気軽にメモしてください</span>
            </div>
          ) : (
            <>
              <div aria-hidden="true" className={styles.colHead}>
                <span>種別</span>
                <span>メモ</span>
                <span>#</span>
                <span>登録日時</span>
                <span />
              </div>
              <div
                role="list"
                aria-label="inboxの項目（登録日時の新しい順）"
                className={styles.list}
              >
                {sorted.map((it) => (
                  <div role="listitem" key={it.number}>
                    {editing === it.number ? (
                      <InboxRowEditor
                        repo={repo}
                        item={it}
                        onDone={() => setEditing(null)}
                        onSaved={() => {
                          setEditing(null);
                          onChanged();
                        }}
                      />
                    ) : (
                      <div
                        className={`${styles.row} ${newId === it.number ? styles.rowNew : ""}`}
                      >
                        <span className={styles.kindCell}>
                          <KindBadge kind={it.kind} />
                        </span>
                        <div className={styles.memo}>
                          <a
                            className={styles.memoTitle}
                            href={`https://github.com/${repo}/issues/${it.number}`}
                            target="_blank"
                            rel="noreferrer"
                            title={it.title}
                          >
                            {it.title}
                          </a>
                          {it.body && (
                            <span className={styles.memoSub}>{it.body}</span>
                          )}
                        </div>
                        <span className={styles.num}>#{it.number}</span>
                        <time className={styles.date} dateTime={it.created_at}>
                          {formatAbsoluteTime(it.created_at)}
                        </time>
                        <div className={styles.actions}>
                          <button
                            type="button"
                            className={styles.plan}
                            aria-label={`${repo} #${it.number} を計画する`}
                            title="AIに計画してもらう（承認するとissueに昇格）"
                            onClick={() => openNewTask(repo, it)}
                          >
                            <Icon d={PATHS.sparkle} />
                            計画する
                          </button>
                          <button
                            type="button"
                            className={styles.ghost}
                            aria-label={`${repo} #${it.number} を編集`}
                            onClick={() => setEditing(it.number)}
                          >
                            <Icon d={PATHS.edit} />
                            編集
                          </button>
                          <button
                            type="button"
                            className={`${styles.ghost} ${styles.iconOnly} ${styles.delBtn}`}
                            aria-label={`${repo} #${it.number} を削除`}
                            title="削除"
                            onClick={() => setDeleting(it)}
                          >
                            <Icon d={PATHS.trash} size={14} />
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {deleting && (
        <DeleteDialog
          repo={repo}
          item={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            const d = deleting;
            setDeleting(null);
            showToast(
              `inboxから削除しました（${repo} #${d.number} をクローズ）。`,
            );
            onChanged();
          }}
        />
      )}
    </section>
  );
}
