"use client";

import { useState } from "react";
import type { MatchMode, MetaFilterOption } from "@/lib/issueList";
import { issueTags } from "@/lib/issueList";
import type { ProjectIssue } from "@/lib/types";
import styles from "./MetaFilter.module.css";

/** タグ名ごとのドット色（Artifactsデザインの`TAGC`）。未定義のタグは薄いグレー。 */
const TAG_COLOR_VAR: Record<string, string> = {
  bug: "--warn",
  enhancement: "--accent-blue",
  performance: "--accent-amber",
  documentation: "--accent-gray",
  "good first issue": "--accent-green",
  "needs-repro": "--warn",
  refactor: "--accent-purple",
  chore: "--accent-gray",
};

export function tagDotColor(tag: string): string {
  return `var(${TAG_COLOR_VAR[tag] ?? "--text-tertiary"})`;
}

/** PC幅の行に表示するタグの最大数。超過分は`+N`にまとめる（モバイル幅は折り返して全表示）。 */
const TAG_MAX = 3;

export const FlagIcon = ({ size }: { size: number }) => (
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
    <path d="M12 13v8M12 3v3" />
    <path d="M4 6a1 1 0 0 0-1 1v5a1 1 0 0 0 1 1h13a2 2 0 0 0 1.15-.37l3.43-2.31a1 1 0 0 0 0-1.64L18.15 6.37A2 2 0 0 0 17 6Z" />
  </svg>
);

export const TagIcon = () => (
  <svg
    width="13"
    height="13"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.1"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    style={{ flex: "none" }}
  >
    <path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42Z" />
    <circle cx="7.5" cy="7.5" r="1" fill="currentColor" />
  </svg>
);

const CloseIcon = () => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.4"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    style={{ flex: "none" }}
  >
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
);

const cx = (...names: (string | false | null | undefined)[]) =>
  names.filter(Boolean).join(" ");

/** ボタン上の要約。未選択は「すべて」、複数は「v1.2 +1」形式。 */
function summarize(selected: string[]): string {
  if (selected.length === 0) return "すべて";
  return selected[0] + (selected.length > 1 ? ` +${selected.length - 1}` : "");
}

const ChevronIcon = ({ open }: { open: boolean }) => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.4"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    className={cx(styles.chevron, open && styles.chevronOpen)}
  >
    <path d="m6 9 6 6 6-6" />
  </svg>
);

const InfoIcon = () => (
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
    <circle cx="12" cy="12" r="9" />
    <path d="M12 16v-4M12 8h.01" />
  </svg>
);

interface MultiSelectProps {
  id: string;
  label: string;
  icon: React.ReactNode;
  options: MetaFilterOption[];
  selected: string[];
  open: boolean;
  /** ラジオ表示（ANDのマイルストーンは1つだけ選べる）。 */
  single?: boolean;
  head: string;
  notice?: string | null;
  mono?: boolean;
  showDot?: boolean;
  /** 右寄せ（モバイルで右側のドロップダウンが画面外に出ないようにする）。 */
  alignRight?: boolean;
  onToggleOpen: () => void;
  onClose: () => void;
  onToggle: (value: string) => void;
  onClearGroup: () => void;
}

/** 複数選択できるコンボボックス（ドロップダウン）。 */
function MultiSelect({
  id,
  label,
  icon,
  options,
  selected,
  open,
  single,
  head,
  notice,
  mono,
  showDot,
  alignRight,
  onToggleOpen,
  onClose,
  onToggle,
  onClearGroup,
}: MultiSelectProps) {
  const summary = summarize(selected);
  const aria = `${label}で絞り込み: ${selected.length ? selected.join("、") : "すべて"}${single ? "（ANDでは1つのみ）" : ""}`;
  return (
    <div className={styles.dd}>
      <button
        type="button"
        className={cx(
          styles.trigger,
          selected.length > 0 && styles.triggerOn,
          open && styles.triggerOpen,
        )}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={`${id}-pop`}
        aria-label={aria}
        title={aria}
        onClick={onToggleOpen}
      >
        <span className={styles.triggerIcon}>{icon}</span>
        <span className={styles.triggerLabel}>{label}</span>
        <span
          className={cx(
            styles.summary,
            mono && styles.summaryMono,
            selected.length === 0 && styles.summaryEmpty,
          )}
        >
          {summary}
        </span>
        <span style={{ flex: 1 }} />
        <ChevronIcon open={open} />
      </button>
      {open && (
        <div
          id={`${id}-pop`}
          role="dialog"
          aria-label={`${label}を選択`}
          className={cx(styles.pop, alignRight && styles.popRight)}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
          }}
        >
          <div className={styles.popHead}>
            {single && (
              <span className={styles.noticeIcon}>
                <InfoIcon />
              </span>
            )}
            <span>{head}</span>
          </div>
          {notice && (
            <div className={styles.notice} role="status" aria-live="polite">
              <span className={styles.noticeIcon}>
                <InfoIcon />
              </span>
              <span style={{ textWrap: "pretty" }}>{notice}</span>
            </div>
          )}
          <div className={styles.list} role="group" aria-label={label}>
            {options.map((o) => {
              const on = selected.includes(o.value);
              return (
                <button
                  key={o.value}
                  type="button"
                  aria-pressed={on}
                  className={cx(styles.opt, on && styles.optOn)}
                  title={
                    single && !on && selected.length > 0
                      ? "ANDではマイルストーンは1つだけ選べます（選択中のものと入れ替わります）"
                      : undefined
                  }
                  onClick={() => onToggle(o.value)}
                >
                  <span
                    className={cx(
                      styles.box,
                      single && styles.boxRadio,
                      on && styles.boxOn,
                    )}
                  >
                    {on &&
                      (single ? (
                        <span className={styles.radioDot} />
                      ) : (
                        <svg
                          width="11"
                          height="11"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="3.4"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          aria-hidden="true"
                        >
                          <path d="M20 6 9 17l-5-5" />
                        </svg>
                      ))}
                  </span>
                  {showDot && (
                    <span
                      className={styles.dot}
                      style={{ background: tagDotColor(o.value) }}
                    />
                  )}
                  <span
                    className={cx(
                      styles.optName,
                      mono && styles.optNameMono,
                      o.count === 0 && !on && styles.optNameEmpty,
                    )}
                  >
                    {o.value}
                  </span>
                  <span className={styles.optCount}>{o.count}</span>
                </button>
              );
            })}
          </div>
          <div className={styles.popFoot}>
            {selected.length > 0 && (
              <button
                type="button"
                className={styles.popBtn}
                onClick={onClearGroup}
              >
                <CloseIcon />
                選択を解除
              </button>
            )}
            <span style={{ flex: 1 }} />
            <button
              type="button"
              className={styles.popBtnDim}
              onClick={onClose}
            >
              閉じる
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

interface MetaFilterProps {
  milestones: MetaFilterOption[];
  tags: MetaFilterOption[];
  selectedMilestones: string[];
  selectedTags: string[];
  mode: MatchMode;
  /** ANDでマイルストーンを入れ替えたときの注記（マイルストーンのドロップダウン内に表示）。 */
  notice: string | null;
  onToggleMilestone: (milestone: string) => void;
  onToggleTag: (tag: string) => void;
  onClearMilestones: () => void;
  onClearTags: () => void;
  onModeChange: (mode: MatchMode) => void;
  onClear: () => void;
  /** ドロップダウンを閉じたときに注記を消す。 */
  onCloseDropdown: () => void;
}

/** ツールバー下のマイルストーン・タグのコンボボックスと、OR/ANDトグル（issue #303）。PC幅は1行固定。 */
export function MetaFilter({
  milestones,
  tags,
  selectedMilestones,
  selectedTags,
  mode,
  notice,
  onToggleMilestone,
  onToggleTag,
  onClearMilestones,
  onClearTags,
  onModeChange,
  onClear,
  onCloseDropdown,
}: MetaFilterProps) {
  const [open, setOpen] = useState<"ms" | "tg" | null>(null);
  if (milestones.length === 0 && tags.length === 0) return null;
  const selectedCount = selectedMilestones.length + selectedTags.length;
  const segOff = selectedCount < 2;
  const isAnd = mode === "and";
  const close = () => {
    setOpen(null);
    onCloseDropdown();
  };
  const toggleOpen = (g: "ms" | "tg") => {
    if (open === g) close();
    else setOpen(g);
  };
  const modeDesc = segOff
    ? "2つ以上選ぶと切替可"
    : isAnd
      ? "すべてに一致"
      : "いずれかに一致";
  const modeTitle = segOff
    ? "条件を2つ以上選ぶと OR / AND を切り替えられます"
    : isAnd
      ? "選んだ条件のすべてに一致"
      : "選んだ条件のいずれかに一致";

  return (
    <>
      {open && (
        <div className={styles.catcher} onClick={close} aria-hidden="true" />
      )}
      <div
        className={cx(styles.wrap, open && styles.wrapOpen)}
        role="group"
        aria-label="マイルストーン・タグで絞り込み"
      >
        {milestones.length > 0 && (
          <MultiSelect
            id="mt-ms"
            label="マイルストーン"
            icon={<FlagIcon size={13} />}
            options={milestones}
            selected={selectedMilestones}
            open={open === "ms"}
            single={isAnd}
            head={isAnd ? "ANDでは1つのみ選択できます" : "複数選択できます"}
            notice={notice}
            mono
            onToggleOpen={() => toggleOpen("ms")}
            onClose={close}
            onToggle={onToggleMilestone}
            onClearGroup={onClearMilestones}
          />
        )}
        {tags.length > 0 && (
          <MultiSelect
            id="mt-tg"
            label="タグ"
            icon={<TagIcon />}
            options={tags}
            selected={selectedTags}
            open={open === "tg"}
            head="複数選択できます"
            showDot
            alignRight
            onToggleOpen={() => toggleOpen("tg")}
            onClose={close}
            onToggle={onToggleTag}
            onClearGroup={onClearTags}
          />
        )}
        <span className={styles.divider} />
        <div className={styles.combo}>
          <div
            className={cx(styles.seg, segOff && styles.segOff)}
            role="group"
            aria-label="複数条件の結合方法"
            title={modeTitle}
          >
            {(["or", "and"] as const).map((m) => (
              <button
                key={m}
                type="button"
                disabled={segOff}
                aria-pressed={mode === m}
                className={cx(styles.segBtn, mode === m && styles.segBtnOn)}
                onClick={() => onModeChange(m)}
              >
                {m === "or" ? "OR" : "AND"}
              </button>
            ))}
          </div>
          <span
            className={cx(styles.desc, segOff && styles.descOff)}
            aria-live="polite"
            title={modeTitle}
          >
            {modeDesc}
          </span>
        </div>
        {selectedCount > 0 && (
          <button type="button" className={styles.clear} onClick={onClear}>
            <CloseIcon />
            条件を解除（{selectedCount}）
          </button>
        )}
      </div>
    </>
  );
}

/** issue行（タイトルセル2行目）・カードに表示するマイルストーンとタグのチップ。 */
export function IssueMeta({
  issue,
  selectedMilestones,
  selectedTags,
}: {
  issue: ProjectIssue;
  selectedMilestones: string[];
  selectedTags: string[];
}) {
  const tags = issueTags(issue);
  if (!issue.milestone && tags.length === 0) return null;
  const rest = tags.slice(TAG_MAX);
  return (
    <div className={styles.line}>
      {issue.milestone && (
        <span
          className={cx(
            styles.rowChip,
            styles.rowChipMs,
            selectedMilestones.includes(issue.milestone) && styles.rowChipOn,
          )}
          title={`マイルストーン: ${issue.milestone}`}
        >
          <FlagIcon size={11} />
          {issue.milestone}
        </span>
      )}
      {tags.map((t, index) => (
        <span
          key={t}
          className={cx(
            styles.rowChip,
            index >= TAG_MAX && styles.rowChipExtra,
            selectedTags.includes(t) && styles.rowChipOn,
          )}
        >
          <span
            className={styles.rowDot}
            style={{ background: tagDotColor(t) }}
          />
          {t}
        </span>
      ))}
      {rest.length > 0 && (
        <span
          className={cx(
            styles.rowChip,
            styles.rowChipMore,
            rest.some((t) => selectedTags.includes(t)) && styles.rowChipOn,
          )}
          title={`他のタグ: ${rest.join(", ")}`}
          aria-label={`他のタグ: ${rest.join(", ")}`}
        >
          +{rest.length}
        </span>
      )}
    </div>
  );
}
