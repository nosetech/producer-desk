"use client";

import { useEffect, useState } from "react";
import {
  canApplyMeta,
  isMetaDraftEmpty,
  toggleLabelChoice,
  type MetaDraft,
} from "@/lib/issueMeta";
import type { MilestoneChange, ProjectIssue } from "@/lib/types";
import { issueTags } from "@/lib/issueList";
import { FlagIcon, IssueMeta, TagIcon, tagDotColor } from "./MetaFilter";
import styles from "./BulkEdit.module.css";

const cx = (...names: (string | false | null | undefined)[]) =>
  names.filter(Boolean).join(" ");

/** マイルストーン・ラベル一覧を取得できないときの理由（変更UIを無効にする）。 */
export const OPTIONS_UNAVAILABLE_REASON =
  "マイルストーン・ラベルの一覧を取得できませんでした。再取得してからもう一度お試しください。";
const OPTIONS_UNAVAILABLE_SHORT =
  "マイルストーン・ラベルの一覧を取得できないため編集できません";

function Svg({
  size,
  strokeWidth = 2.2,
  children,
}: {
  size: number;
  strokeWidth?: number;
  children: React.ReactNode;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flex: "none" }}
    >
      {children}
    </svg>
  );
}

const CheckIcon = ({ size }: { size: number }) => (
  <Svg size={size} strokeWidth={size > 12 ? 2.6 : 3.4}>
    <path d="M20 6 9 17l-5-5" />
  </Svg>
);

export const WarnTriangle = ({ size }: { size: number }) => (
  <Svg size={size} strokeWidth={2.4}>
    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
    <path d="M12 9v4M12 17h.01" />
  </Svg>
);

function ApplySpinner() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 42 42"
      aria-hidden="true"
      className={styles.spinner}
    >
      <circle
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="rgba(255,255,255,.32)"
        strokeWidth="5"
      />
      <circle
        cx="21"
        cy="21"
        r="17"
        fill="none"
        stroke="#fff"
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray="34 200"
        className={styles.spinnerArc}
      />
    </svg>
  );
}

function CreateGuide({ repo }: { repo: string }) {
  const link = (path: string, text: string) => (
    <a
      className={styles.guideLink}
      href={`https://github.com/${repo}/${path}`}
      target="_blank"
      rel="noreferrer"
    >
      {text}
      <Svg size={10} strokeWidth={2.4}>
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
        <path d="M15 3h6v6M10 14 21 3" />
      </Svg>
    </a>
  );
  return (
    <div className={styles.guide}>
      <Svg size={12}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 16v-4M12 8h.01" />
      </Svg>
      <span>
        新しく作るにはGitHubで作成してください（
        {link("milestones", "マイルストーン")}・{link("labels", "ラベル")}）
      </span>
    </div>
  );
}

function OptBox({
  on,
  radio,
  tone,
}: {
  on: boolean;
  radio?: boolean;
  tone?: "warn";
}) {
  return (
    <span
      className={cx(
        styles.box,
        radio && styles.boxRadio,
        on && (tone === "warn" ? styles.boxOnWarn : styles.boxOn),
      )}
    >
      {on &&
        (radio ? (
          <span className={styles.radioDot} />
        ) : (
          <CheckIcon size={11} />
        ))}
    </span>
  );
}

interface OptionProps {
  on: boolean;
  disabled?: boolean;
  radio?: boolean;
  tone?: "warn";
  dot?: string;
  name: string;
  mono?: boolean;
  count?: string;
  title?: string;
  onClick: () => void;
}

function Option({
  on,
  disabled,
  radio,
  tone,
  dot,
  name,
  mono,
  count,
  title,
  onClick,
}: OptionProps) {
  return (
    <button
      type="button"
      className={cx(styles.opt, on && styles.optOn)}
      aria-pressed={on}
      disabled={disabled}
      title={title}
      onClick={onClick}
    >
      <OptBox on={on} radio={radio} tone={tone} />
      {dot && <span className={styles.optDot} style={{ background: dot }} />}
      <span className={cx(styles.optName, mono && styles.optNameMono)}>
        {name}
      </span>
      {count && <span className={styles.optCount}>{count}</span>}
    </button>
  );
}

function sumList(arr: readonly string[], none: string): string {
  return arr.length === 0
    ? none
    : arr[0] + (arr.length > 1 ? ` +${arr.length - 1}` : "");
}

type OpenKey = "ms" | "add" | "rem" | null;

interface BulkBarProps {
  repo: string;
  /** 選択中のissue（現在の一覧に存在するもの）。 */
  selected: ProjectIssue[];
  milestones: string[] | null;
  labels: string[] | null;
  onApply: (draft: MetaDraft) => Promise<void>;
  onClear: () => void;
}

/** 選択したissueへマイルストーン・ラベルをまとめて設定する一括操作バー（issue #305）。 */
export function BulkBar({
  repo,
  selected,
  milestones,
  labels,
  onApply,
  onClear,
}: BulkBarProps) {
  const [ms, setMs] = useState<MilestoneChange>({ mode: "keep" });
  const [add, setAdd] = useState<string[]>([]);
  const [rem, setRem] = useState<string[]>([]);
  const [open, setOpen] = useState<OpenKey>(null);
  const [applying, setApplying] = useState(false);

  const optErr = milestones === null || labels === null;
  const n = selected.length;
  const nums = new Set(selected.map((i) => i.number));
  const draft: MetaDraft = { milestone: ms, addLabels: add, removeLabels: rem };
  const noChange = isMetaDraftEmpty(draft);
  const applyOff = applying || optErr || !canApplyMeta(nums, draft);
  const have = (pred: (i: ProjectIssue) => boolean) =>
    `${selected.filter(pred).length}/${n}`;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // モバイル幅では画面下部固定のシートになるため、トースト・余白の位置をずらす目印を付ける。
  useEffect(() => {
    document.body.dataset.bulkBar = "1";
    return () => {
      delete document.body.dataset.bulkBar;
    };
  }, []);

  const toggleOpen = (k: Exclude<OpenKey, null>) => {
    if (optErr || applying) return;
    setOpen(open === k ? null : k);
  };
  const toggleLabel = (list: "add" | "remove", label: string) => {
    const next = toggleLabelChoice(list, label, add, rem);
    setAdd(next.add);
    setRem(next.remove);
  };

  const apply = async () => {
    if (applyOff) return;
    setOpen(null);
    setApplying(true);
    try {
      await onApply(draft);
    } finally {
      setApplying(false);
    }
  };

  const msSum =
    ms.mode === "keep"
      ? "変更しない"
      : ms.mode === "clear"
        ? "解除する"
        : `→ ${ms.value}`;
  const trigTitle = optErr ? OPTIONS_UNAVAILABLE_REASON : undefined;

  const labelOptions = (list: "add" | "remove") =>
    (labels ?? []).map((t) => {
      const mine = list === "add" ? add : rem;
      const other = list === "add" ? rem : add;
      const blocked = other.includes(t);
      return (
        <Option
          key={t}
          on={mine.includes(t)}
          disabled={blocked}
          tone={list === "remove" ? "warn" : undefined}
          dot={tagDotColor(t)}
          name={t}
          count={
            blocked
              ? list === "add"
                ? "削除に指定中"
                : "追加に指定中"
              : have((i) => issueTags(i).includes(t))
          }
          title={
            blocked
              ? "同じラベルを追加と削除の両方には指定できません"
              : undefined
          }
          onClick={() => toggleLabel(list, t)}
        />
      );
    });

  const popover = (k: "add" | "remove", head: string, aria: string) => (
    <div
      role="dialog"
      aria-label={aria}
      className={cx(styles.pop, k === "remove" && styles.popRight)}
    >
      <div className={styles.popHead}>{head}</div>
      <div className={styles.list}>{labelOptions(k)}</div>
      <CreateGuide repo={repo} />
      <div className={styles.foot}>
        <button
          type="button"
          className={styles.popBtnDim}
          onClick={() => setOpen(null)}
        >
          閉じる
        </button>
      </div>
    </div>
  );

  const clearBtn = (
    <button
      type="button"
      className={styles.clearBtn}
      disabled={applying}
      onClick={onClear}
    >
      <Svg size={12} strokeWidth={2.4}>
        <path d="M18 6 6 18M6 6l12 12" />
      </Svg>
      選択解除
    </button>
  );

  return (
    <>
      {open && (
        <div
          className={styles.catcher}
          aria-hidden="true"
          onClick={() => setOpen(null)}
        />
      )}
      <div
        role="region"
        aria-label="選択したissueの一括操作"
        aria-busy={applying}
        className={cx(styles.bar, open && styles.barOpen)}
      >
        <div className={styles.headRow}>
          <span role="status" aria-live="polite" className={styles.countChip}>
            {n}件選択中
          </span>
          {optErr && (
            <span
              className={styles.warnNote}
              title={OPTIONS_UNAVAILABLE_REASON}
            >
              <WarnTriangle size={12} />
              選択肢を取得できません
            </span>
          )}
          <span className={styles.mobileOnly}>
            <span style={{ flex: 1 }} />
            {clearBtn}
          </span>
        </div>
        <span className={styles.divider} aria-hidden="true" />

        <div className={cx(styles.ddWrap, styles.ddWrapMs)}>
          <button
            type="button"
            className={cx(
              styles.trigger,
              ms.mode !== "keep" && styles.triggerOn,
              open === "ms" && styles.triggerOpen,
            )}
            disabled={optErr || applying}
            aria-haspopup="true"
            aria-expanded={open === "ms"}
            title={trigTitle}
            onClick={() => toggleOpen("ms")}
          >
            <span className={styles.triggerIcon}>
              <FlagIcon size={13} />
            </span>
            <span className={styles.lbl}>マイルストーン</span>
            <span className={styles.sum}>{msSum}</span>
            <span style={{ flex: 1 }} />
            <span className={cx(styles.chev, open === "ms" && styles.chevOpen)}>
              <Svg size={12} strokeWidth={2.4}>
                <path d="m6 9 6 6 6-6" />
              </Svg>
            </span>
          </button>
          {open === "ms" && (
            <div
              role="dialog"
              aria-label="マイルストーンの変更"
              className={styles.pop}
            >
              <div className={styles.popHead}>
                選択中の{n}件に適用 · 右の数字は現在の該当件数
              </div>
              <div className={styles.list}>
                <Option
                  on={ms.mode === "keep"}
                  radio
                  name="変更しない"
                  onClick={() => setMs({ mode: "keep" })}
                />
                <Option
                  on={ms.mode === "clear"}
                  radio
                  name="解除する"
                  count={`ありの${have((i) => !!i.milestone)}`}
                  onClick={() => setMs({ mode: "clear" })}
                />
                <div className={styles.sep} />
                <div className={styles.secHead}>設定する</div>
                {(milestones ?? []).map((m) => (
                  <Option
                    key={m}
                    on={ms.mode === "set" && ms.value === m}
                    radio
                    mono
                    name={m}
                    count={have((i) => i.milestone === m)}
                    onClick={() => setMs({ mode: "set", value: m })}
                  />
                ))}
                {(milestones ?? []).length === 0 && (
                  <div className={styles.guide}>
                    オープン中のマイルストーンはありません
                  </div>
                )}
              </div>
              <CreateGuide repo={repo} />
              <div className={styles.foot}>
                <button
                  type="button"
                  className={styles.popBtnDim}
                  onClick={() => setOpen(null)}
                >
                  閉じる
                </button>
              </div>
            </div>
          )}
        </div>

        <div className={styles.ddWrap}>
          <button
            type="button"
            className={cx(
              styles.trigger,
              add.length > 0 && styles.triggerOn,
              open === "add" && styles.triggerOpen,
            )}
            disabled={optErr || applying}
            aria-haspopup="true"
            aria-expanded={open === "add"}
            title={trigTitle}
            onClick={() => toggleOpen("add")}
          >
            <span className={styles.triggerIcon}>
              <TagIcon />
            </span>
            <span className={styles.lbl}>ラベル追加</span>
            <span className={styles.sum}>{sumList(add, "なし")}</span>
            <span style={{ flex: 1 }} />
            <span
              className={cx(styles.chev, open === "add" && styles.chevOpen)}
            >
              <Svg size={12} strokeWidth={2.4}>
                <path d="m6 9 6 6 6-6" />
              </Svg>
            </span>
          </button>
          {open === "add" &&
            popover(
              "add",
              "追加するラベル（複数選択） · 右は付いている件数",
              "追加するラベル",
            )}
        </div>

        <div className={styles.ddWrap}>
          <button
            type="button"
            className={cx(
              styles.trigger,
              rem.length > 0 && styles.triggerOn,
              open === "rem" && styles.triggerOpen,
            )}
            disabled={optErr || applying}
            aria-haspopup="true"
            aria-expanded={open === "rem"}
            title={trigTitle}
            onClick={() => toggleOpen("rem")}
          >
            <span className={styles.triggerIcon}>
              <TagIcon />
            </span>
            <span className={styles.lbl}>ラベル削除</span>
            <span className={styles.sum}>{sumList(rem, "なし")}</span>
            <span style={{ flex: 1 }} />
            <span
              className={cx(styles.chev, open === "rem" && styles.chevOpen)}
            >
              <Svg size={12} strokeWidth={2.4}>
                <path d="m6 9 6 6 6-6" />
              </Svg>
            </span>
          </button>
          {open === "rem" &&
            popover(
              "remove",
              "削除するラベル（複数選択） · 右は付いている件数",
              "削除するラベル",
            )}
        </div>

        <span className={styles.spacer} aria-hidden="true" />
        <span className={styles.desktopOnly}>{clearBtn}</span>
        <button
          type="button"
          className={styles.applyBtn}
          disabled={applyOff}
          aria-busy={applying}
          title={
            optErr
              ? OPTIONS_UNAVAILABLE_REASON
              : noChange
                ? "変更内容を指定してください"
                : `${n}件に適用`
          }
          onClick={() => void apply()}
        >
          {applying ? <ApplySpinner /> : <CheckIcon size={14} />}
          {applying ? "適用中…" : "適用"}
        </button>
      </div>
    </>
  );
}

interface IssueMetaCellProps {
  repo: string;
  issue: ProjectIssue;
  milestones: string[] | null;
  labels: string[] | null;
  selectedMilestones: string[];
  selectedTags: string[];
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  /** 戻り値のPromiseが解決したら閉じる。 */
  onApply: (draft: MetaDraft) => Promise<void>;
}

/** 行・カードのマイルストーン/タグ表示。クリックで個別編集ポップオーバーを開く（issue #305）。 */
export function IssueMetaCell({
  repo,
  issue,
  milestones,
  labels,
  selectedMilestones,
  selectedTags,
  open,
  onOpen,
  onClose,
  onApply,
}: IssueMetaCellProps) {
  const optErr = milestones === null || labels === null;
  const noMeta = !issue.milestone && issueTags(issue).length === 0;
  return (
    <div className={styles.metaCell}>
      <button
        type="button"
        className={cx(styles.metaBtn, open && styles.metaBtnOpen)}
        disabled={optErr}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`#${issue.number} のマイルストーン・ラベルを編集`}
        title={
          optErr ? OPTIONS_UNAVAILABLE_SHORT : "マイルストーン・ラベルを編集"
        }
        onClick={() => (open ? onClose() : onOpen())}
      >
        <IssueMeta
          issue={issue}
          selectedMilestones={selectedMilestones}
          selectedTags={selectedTags}
        />
        {noMeta && (
          <span className={styles.addChip}>
            <Svg size={10} strokeWidth={3}>
              <path d="M12 5v14M5 12h14" />
            </Svg>
            マイルストーン・ラベル
          </span>
        )}
      </button>
      {open && !optErr && (
        <MetaEditPopover
          repo={repo}
          issue={issue}
          milestones={milestones}
          labels={labels}
          onClose={onClose}
          onApply={onApply}
        />
      )}
    </div>
  );
}

function MetaEditPopover({
  repo,
  issue,
  milestones,
  labels,
  onClose,
  onApply,
}: {
  repo: string;
  issue: ProjectIssue;
  milestones: string[];
  labels: string[];
  onClose: () => void;
  onApply: (draft: MetaDraft) => Promise<void>;
}) {
  const [ms, setMs] = useState<string | null>(issue.milestone ?? null);
  const [tags, setTags] = useState<string[]>(issueTags(issue));
  const [applying, setApplying] = useState(false);
  // 現在の値は（クローズ済みマイルストーンや一覧に無いラベルでも）表示し、勝手に外さない。
  const msOptions =
    issue.milestone && !milestones.includes(issue.milestone)
      ? [issue.milestone, ...milestones]
      : milestones;
  const labelOptions = [
    ...labels,
    ...issueTags(issue).filter((t) => !labels.includes(t)),
  ];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !applying) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [applying, onClose]);

  const apply = async () => {
    if (applying) return;
    const draft: MetaDraft = {
      milestone:
        ms === (issue.milestone ?? null)
          ? { mode: "keep" }
          : ms === null
            ? { mode: "clear" }
            : { mode: "set", value: ms },
      addLabels: tags.filter((t) => !issueTags(issue).includes(t)),
      removeLabels: issueTags(issue).filter((t) => !tags.includes(t)),
    };
    if (isMetaDraftEmpty(draft)) {
      onClose();
      return;
    }
    setApplying(true);
    try {
      await onApply(draft);
    } finally {
      setApplying(false);
    }
  };

  const title = `#${issue.number} のマイルストーン・ラベル`;
  return (
    <>
      <div
        className={cx(styles.catcher, styles.catcherEdit)}
        aria-hidden="true"
        onClick={() => !applying && onClose()}
      />
      <div role="dialog" aria-label={title} className={styles.editPop}>
        <div className={styles.popHead}>
          <span className={styles.editTitle}>{title}</span>
        </div>
        <div className={styles.list}>
          <div className={styles.secHead}>マイルストーン（1つ）</div>
          <Option
            on={ms === null}
            radio
            name="なし（解除）"
            onClick={() => setMs(null)}
          />
          {msOptions.map((m) => (
            <Option
              key={m}
              on={ms === m}
              radio
              mono
              name={m}
              onClick={() => setMs(m)}
            />
          ))}
          {msOptions.length === 0 && (
            <div className={styles.guide}>
              オープン中のマイルストーンはありません
            </div>
          )}
          <div className={styles.sep} />
          <div className={styles.secHead}>ラベル（複数選択）</div>
          {labelOptions.map((t) => (
            <Option
              key={t}
              on={tags.includes(t)}
              dot={tagDotColor(t)}
              name={t}
              onClick={() =>
                setTags(
                  tags.includes(t) ? tags.filter((x) => x !== t) : [...tags, t],
                )
              }
            />
          ))}
        </div>
        <CreateGuide repo={repo} />
        <div className={styles.foot}>
          <button
            type="button"
            className={cx(styles.popBtnDim, styles.editBtn)}
            disabled={applying}
            onClick={onClose}
          >
            キャンセル
          </button>
          <button
            type="button"
            className={cx(styles.applyBtn, styles.editBtn)}
            disabled={applying}
            aria-busy={applying}
            onClick={() => void apply()}
          >
            {applying ? <ApplySpinner /> : <CheckIcon size={14} />}
            {applying ? "適用中…" : "適用"}
          </button>
        </div>
      </div>
    </>
  );
}
