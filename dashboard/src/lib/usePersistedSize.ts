"use client";

import { useCallback, useRef } from "react";
import {
  clampSize,
  loadPanelSizes,
  maxPanelSizeCss,
  savePanelSize,
  type PanelKey,
} from "./panelSizes";

// BottomNav に切り替わる幅。この幅以下では横方向のリサイズを無効にする。
const MOBILE_MAX_WIDTH = 640;

// ブラウザ標準のリサイズハンドルが占める右下の領域（px）。
const GRIP_SIZE = 20;

type Axes = "width" | "height";

/**
 * CSS の `resize` で変更した要素サイズを localStorage に保存し、マウント時に復元する。
 * 返り値は対象要素に付ける callback ref。保存はユーザーがドラッグしてサイズが変わったときだけ行う。
 */
export function usePersistedSize(
  key: PanelKey,
  axes: readonly Axes[],
  {
    // 親の中で自分以外が占める高さを上限から差し引く（親が overflow: hidden のモーダル本文用）。
    fitParent = false,
    // CSS 側の max-*（含む領域基準で viewport 内に収まるもの）をそのまま使う。
    keepMax = false,
    // 保存値の復元だけを行い、標準リサイズハンドルのドラッグは扱わない（辺ドラッグ側で保存する場合）。
    restoreOnly = false,
  }: { fitParent?: boolean; keepMax?: boolean; restoreOnly?: boolean } = {},
) {
  const cleanup = useRef<(() => void) | null>(null);
  const axesKey = axes.join(",");

  return useCallback(
    (el: HTMLElement | null) => {
      cleanup.current?.();
      cleanup.current = null;
      if (!el) return;
      const target = axesKey.split(",") as Axes[];
      const isMobile = () => window.innerWidth <= MOBILE_MAX_WIDTH;
      const reserved = () =>
        fitParent && el.parentElement
          ? Math.max(0, el.parentElement.offsetHeight - el.offsetHeight)
          : 0;
      const setMax = (axis: Axes) => {
        if (keepMax) return;
        if (axis === "width") el.style.maxWidth = maxPanelSizeCss("width");
        else el.style.maxHeight = maxPanelSizeCss("height", reserved());
      };
      const active = () =>
        target.filter((axis) => axis === "height" || !isMobile());

      // 保存値の復元。固定値の max-* は viewport 由来の上限に置き換え、flex は外して保存サイズを優先する。
      const saved = loadPanelSizes()[key];
      if (saved) {
        for (const axis of active()) {
          const value = saved[axis];
          if (value === undefined) continue;
          const viewport =
            axis === "width" ? window.innerWidth : window.innerHeight;
          const extra = axis === "height" ? reserved() : 0;
          el.style[axis] = `${clampSize(value, viewport, extra)}px`;
          setMax(axis);
          el.style.flex = fitParent ? "0 1 auto" : "none";
        }
      }

      // ドラッグ中は固定の max-*/flex が上限になってしまうため、押下時に現在の px 値を
      // インラインで固定し、固定の max-* は viewport 由来の上限に置き換える。サイズが変わらなかった場合は元のスタイルへ戻す。
      const props = [
        "width",
        "height",
        "maxWidth",
        "maxHeight",
        "flex",
      ] as const;
      let start: {
        width: number;
        height: number;
        style: Record<(typeof props)[number], string>;
      } | null = null;
      const onDown = (e: PointerEvent) => {
        const rect = el.getBoundingClientRect();
        if (rect.right - e.clientX > GRIP_SIZE) return;
        if (rect.bottom - e.clientY > GRIP_SIZE) return;
        const style = Object.fromEntries(
          props.map((prop) => [prop, el.style[prop]]),
        ) as Record<(typeof props)[number], string>;
        start = { width: el.offsetWidth, height: el.offsetHeight, style };
        for (const axis of active()) {
          el.style[axis] = `${start[axis]}px`;
          setMax(axis);
        }
        el.style.flex = "none";
      };
      const onUp = () => {
        if (!start) return;
        const before = start;
        start = null;
        const next = { width: el.offsetWidth, height: el.offsetHeight };
        if (next.width === before.width && next.height === before.height) {
          for (const prop of props) el.style[prop] = before.style[prop];
          return;
        }
        const size: { width?: number; height?: number } = {};
        for (const axis of active()) size[axis] = next[axis];
        savePanelSize(key, { ...loadPanelSizes()[key], ...size });
      };
      if (restoreOnly) return;
      el.addEventListener("pointerdown", onDown);
      window.addEventListener("pointerup", onUp);
      cleanup.current = () => {
        el.removeEventListener("pointerdown", onDown);
        window.removeEventListener("pointerup", onUp);
      };
    },
    [key, axesKey, fitParent, keepMax, restoreOnly],
  );
}
