"use client";

import { useCallback, useRef } from "react";
import {
  clampSize,
  loadPanelSizes,
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
export function usePersistedSize(key: PanelKey, axes: readonly Axes[]) {
  const cleanup = useRef<(() => void) | null>(null);
  const axesKey = axes.join(",");

  return useCallback(
    (el: HTMLElement | null) => {
      cleanup.current?.();
      cleanup.current = null;
      if (!el) return;
      const target = axesKey.split(",") as Axes[];
      const isMobile = () => window.innerWidth <= MOBILE_MAX_WIDTH;
      const active = () =>
        target.filter((axis) => axis === "height" || !isMobile());

      // 保存値の復元。固定値の max-*/flex をインラインで外し、保存サイズを優先する。
      const saved = loadPanelSizes()[key];
      if (saved) {
        for (const axis of active()) {
          const value = saved[axis];
          if (value === undefined) continue;
          const viewport =
            axis === "width" ? window.innerWidth : window.innerHeight;
          el.style[axis] = `${clampSize(value, viewport)}px`;
          if (axis === "width") el.style.maxWidth = "none";
          else el.style.maxHeight = "none";
          el.style.flex = "none";
        }
      }

      // ドラッグ中は固定の max-*/flex が上限になってしまうため、押下時に現在の px 値を
      // インラインで固定して上限を外す。サイズが変わらなかった場合は元のスタイルへ戻す。
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
          if (axis === "width") el.style.maxWidth = "none";
          else el.style.maxHeight = "none";
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
      el.addEventListener("pointerdown", onDown);
      window.addEventListener("pointerup", onUp);
      cleanup.current = () => {
        el.removeEventListener("pointerdown", onDown);
        window.removeEventListener("pointerup", onUp);
      };
    },
    [key, axesKey],
  );
}
