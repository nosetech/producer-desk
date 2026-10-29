"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  buildQueueItems,
  isQueueEmpty,
  queueAriaLabel,
  queuePositionText,
  truncateQueueTitle,
} from "@/lib/queue";
import { statusMeta } from "@/lib/status";
import type { ProjectQueue as ProjectQueueData, QueueEntry } from "@/lib/types";
import { CloseIcon } from "./Icons";
import styles from "./ProjectQueue.module.css";

const TIP_WIDTH = 260;

interface TipState {
  key: string;
  entry: QueueEntry;
  isRunning: boolean;
  position: number;
  pinned: boolean;
  rect: { x: number; top: number; bottom: number };
}

/**
 * プロジェクトチップ内のディスパッチキューのミニ図（issue #233）。Claude Designの
 * `buildQueue`・`qtip`に対応する。実行中1件を先頭に、待機中をFIFO順に並べ、
 * ホバー/フォーカス/タップでissueの内容をツールチップ表示する。
 */
export default function ProjectQueue({
  repo,
  queue,
}: {
  repo: string;
  queue: ProjectQueueData;
}) {
  const [tip, setTip] = useState<TipState | null>(null);
  const [isTouch, setIsTouch] = useState(false);
  const items = buildQueueItems(queue);
  const empty = isQueueEmpty(queue);

  useEffect(() => {
    if (!tip) return;
    const close = () => setTip(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [tip]);

  const open = (
    el: HTMLElement,
    key: string,
    entry: QueueEntry,
    isRunning: boolean,
    position: number,
    pinned: boolean,
  ) => {
    const r = el.getBoundingClientRect();
    setTip({
      key,
      entry,
      isRunning,
      position,
      pinned,
      rect: { x: r.left + r.width / 2, top: r.top, bottom: r.bottom },
    });
  };
  const closeUnpinned = () => setTip((t) => (t && !t.pinned ? null : t));

  return (
    <>
      <div
        role="list"
        aria-label={queueAriaLabel(repo, queue)}
        className={empty ? `${styles.lane} ${styles.laneEmpty}` : styles.lane}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        {items.map((item, i) => {
          if (item.kind === "sep")
            return <span key={`sep${i}`} aria-hidden className={styles.sep} />;
          if (item.kind === "slot")
            return (
              <span
                key="slot"
                aria-hidden
                title="実行中のタスクなし"
                className={styles.slot}
              >
                <span className={styles.slotInner} />
              </span>
            );
          if (item.kind === "more")
            return (
              <span
                key="more"
                role="listitem"
                className={styles.more}
                title={`ほか ${item.count}件が待機中（${item.numbers.map((n) => `#${n}`).join(", ")}）`}
              >
                +{item.count}
              </span>
            );
          const isRunning = item.kind === "running";
          const position = item.kind === "waiting" ? item.position : 0;
          const key = `${repo}:${item.key}`;
          const active = tip?.key === key;
          const pinned = active && tip.pinned;
          const { entry } = item;
          const posText = queuePositionText(isRunning, position);
          const hasInfo = entry.title !== null;
          return (
            <span key={key} role="listitem" className={styles.item}>
              <button
                type="button"
                aria-label={`#${entry.number}${hasInfo ? ` ${entry.title}` : ""} — ${posText}`}
                aria-expanded={pinned}
                className={`${styles.taskButton} ${active ? styles.taskButtonActive : ""} ${pinned ? styles.taskButtonPinned : ""}`}
                onMouseEnter={(e) => {
                  if (!isTouch && !tip?.pinned)
                    open(
                      e.currentTarget,
                      key,
                      entry,
                      isRunning,
                      position,
                      false,
                    );
                }}
                onMouseLeave={() => {
                  if (!isTouch) closeUnpinned();
                }}
                onFocus={(e) => {
                  if (!isTouch && !tip?.pinned)
                    open(
                      e.currentTarget,
                      key,
                      entry,
                      isRunning,
                      position,
                      false,
                    );
                }}
                onBlur={closeUnpinned}
                onPointerDown={(e) =>
                  setIsTouch(
                    e.pointerType === "touch" || e.pointerType === "pen",
                  )
                }
                onClick={(e) => {
                  e.stopPropagation();
                  if (pinned) setTip(null);
                  else
                    open(
                      e.currentTarget,
                      key,
                      entry,
                      isRunning,
                      position,
                      true,
                    );
                }}
              >
                {isRunning ? (
                  <>
                    <span aria-hidden className={styles.runRing} />
                    <span aria-hidden className={styles.runDot} />
                  </>
                ) : (
                  <span
                    aria-hidden
                    className={`${styles.waitIcon} ${hasInfo ? "" : styles.waitIconUnknown}`}
                  />
                )}
              </button>
            </span>
          );
        })}
      </div>
      {tip && typeof document !== "undefined"
        ? createPortal(
            <QueueTooltip tip={tip} onClose={() => setTip(null)} repo={repo} />,
            document.body,
          )
        : null}
    </>
  );
}

function QueueTooltip({
  tip,
  repo,
  onClose,
}: {
  tip: TipState;
  repo: string;
  onClose: () => void;
}) {
  const { entry, rect, pinned } = tip;
  const vw = window.innerWidth;
  const below = rect.top < 130;
  const left = Math.max(
    10,
    Math.min(vw - TIP_WIDTH - 10, rect.x - TIP_WIDTH / 2),
  );
  const arrowX = rect.x - left;
  const meta = entry.label ? statusMeta(entry.label) : null;
  return (
    <>
      {pinned && <div className={styles.backdrop} onClick={onClose} />}
      <div
        role="tooltip"
        className={`${styles.tip} ${pinned ? styles.tipPinned : ""}`}
        style={{
          left,
          ...(below
            ? { top: rect.bottom + 9 }
            : { top: rect.top - 9, transform: "translateY(-100%)" }),
        }}
      >
        <span
          aria-hidden
          className={`${styles.arrow} ${below ? styles.arrowUp : styles.arrowDown}`}
          style={{ left: arrowX - 5 }}
        />
        <div className={styles.tipHead}>
          <span className={styles.tipNumber}>#{entry.number}</span>
          <span
            className={`${styles.pos} ${tip.isRunning ? styles.posRunning : ""}`}
          >
            {tip.isRunning && <span className={styles.posDot} />}
            {queuePositionText(tip.isRunning, tip.position)}
          </span>
          <span className={styles.spacer} />
          {pinned && (
            <button
              type="button"
              className={styles.tipClose}
              aria-label="閉じる"
              title="閉じる"
              onClick={onClose}
            >
              <CloseIcon size={13} />
            </button>
          )}
        </div>
        {entry.title !== null && (
          <>
            <div className={styles.tipTitle}>
              {truncateQueueTitle(entry.title)}
            </div>
            <div className={styles.tipMeta}>
              <span
                className={styles.tipBadge}
                style={
                  meta
                    ? {
                        color: `var(${meta.colorVar})`,
                        backgroundColor: `var(${meta.bgVar})`,
                      }
                    : {
                        color: "var(--accent-red)",
                        backgroundColor: "var(--accent-red-bg)",
                      }
                }
              >
                {meta ? meta.text : "ラベルなし"}
              </span>
              <span className={styles.tipRepo}>{repo}</span>
            </div>
          </>
        )}
      </div>
    </>
  );
}
