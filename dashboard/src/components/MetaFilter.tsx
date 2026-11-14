"use client";

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

function tagDotColor(tag: string): string {
  return `var(${TAG_COLOR_VAR[tag] ?? "--text-tertiary"})`;
}

/** PC幅の行に表示するタグの最大数。超過分は`+N`にまとめる（モバイル幅は折り返して全表示）。 */
const TAG_MAX = 3;

const FlagIcon = ({ size }: { size: number }) => (
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

const TagIcon = () => (
  <svg
    width="12"
    height="12"
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

const cx = (...names: (string | false)[]) => names.filter(Boolean).join(" ");

interface MetaFilterProps {
  milestones: MetaFilterOption[];
  tags: MetaFilterOption[];
  selectedMilestones: string[];
  selectedTags: string[];
  mode: MatchMode;
  /** ANDでマイルストーンを1つに絞ったことなどの注記。 */
  notice: string | null;
  onToggleMilestone: (milestone: string) => void;
  onToggleTag: (tag: string) => void;
  onModeChange: (mode: MatchMode) => void;
  onClear: () => void;
}

/** ツールバー下のマイルストーン・タグのフィルタ行と、OR/ANDトグル（issue #303）。 */
export function MetaFilter({
  milestones,
  tags,
  selectedMilestones,
  selectedTags,
  mode,
  notice,
  onToggleMilestone,
  onToggleTag,
  onModeChange,
  onClear,
}: MetaFilterProps) {
  if (milestones.length === 0 && tags.length === 0) return null;
  const selectedCount = selectedMilestones.length + selectedTags.length;
  const segOff = selectedCount < 2;
  const isAnd = mode === "and";
  const modeDesc = segOff
    ? "条件を2つ以上選ぶと切り替えられます"
    : isAnd
      ? "選んだ条件のすべてに一致"
      : "選んだ条件のいずれかに一致";

  return (
    <div
      className={styles.wrap}
      role="group"
      aria-label="マイルストーン・タグで絞り込み"
    >
      {milestones.length > 0 && (
        <div className={styles.row}>
          <span className={styles.label}>
            <FlagIcon size={12} />
            マイルストーン
            {isAnd && milestones.length > 1 && (
              <span
                className={styles.note}
                title="issueのマイルストーンは1つのため、ANDでは1つだけ選べます"
              >
                · 1つのみ
              </span>
            )}
          </span>
          <div
            className={styles.chips}
            role="group"
            aria-label="マイルストーン（複数選択可・ANDでは1つ）"
          >
            {milestones.map((m) => {
              const on = selectedMilestones.includes(m.value);
              return (
                <button
                  key={m.value}
                  type="button"
                  aria-pressed={on}
                  className={cx(
                    styles.chip,
                    styles.chipMs,
                    on && styles.chipOn,
                    m.count === 0 && styles.chipEmpty,
                  )}
                  title={
                    isAnd && !on && selectedMilestones.length > 0
                      ? "ANDではマイルストーンは1つだけ選べます（選択中のものと入れ替わります）"
                      : `マイルストーン「${m.value}」で絞り込む`
                  }
                  onClick={() => onToggleMilestone(m.value)}
                >
                  {m.value}
                  <span className={styles.count}>{m.count}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
      {tags.length > 0 && (
        <div className={styles.row}>
          <span className={styles.label}>
            <TagIcon />
            タグ
          </span>
          <div
            className={styles.chips}
            role="group"
            aria-label="タグ（複数選択可）"
          >
            {tags.map((t) => {
              const on = selectedTags.includes(t.value);
              return (
                <button
                  key={t.value}
                  type="button"
                  aria-pressed={on}
                  className={cx(
                    styles.chip,
                    on && styles.chipOn,
                    t.count === 0 && styles.chipEmpty,
                  )}
                  onClick={() => onToggleTag(t.value)}
                >
                  <span
                    className={styles.dot}
                    style={{ background: tagDotColor(t.value) }}
                  />
                  {t.value}
                  <span className={styles.count}>{t.count}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
      <div className={styles.row}>
        <span className={styles.label}>結合</span>
        <div className={styles.combo}>
          <div
            className={cx(styles.seg, segOff && styles.segOff)}
            role="group"
            aria-label="複数条件の結合方法"
            title={
              segOff
                ? "条件を2つ以上選ぶと OR / AND を切り替えられます"
                : "複数条件の結合方法"
            }
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
          >
            {modeDesc}
          </span>
          {selectedCount > 0 && (
            <button type="button" className={styles.clear} onClick={onClear}>
              <CloseIcon />
              条件を解除（{selectedCount}）
            </button>
          )}
        </div>
      </div>
      {notice && (
        <div className={styles.notice} role="status" aria-live="polite">
          <span className={styles.noticeIcon}>
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
          </span>
          <span style={{ textWrap: "pretty" }}>{notice}</span>
        </div>
      )}
    </div>
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
