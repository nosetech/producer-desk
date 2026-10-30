"use client";

import { useCallback, useRef } from "react";
import {
  EDGE_ZONE,
  clampTop,
  detectEdges,
  edgeCursor,
  resizeByEdges,
  type Edge,
} from "./edgeResize";
import {
  VIEWPORT_MARGIN,
  loadPanelSizes,
  maxPanelSizeCss,
  savePanelSize,
  type PanelKey,
} from "./panelSizes";

// BottomNav に切り替わる幅。この幅以下では左右の辺のリサイズを無効にする。
const MOBILE_MAX_WIDTH = 640;

// 親の中で上下に確保する余白（返信UIパネルの top/bottom の既定値に合わせる）。
const PARENT_MARGIN = VIEWPORT_MARGIN / 2;

type Options = {
  // 指定すると、上下の辺のドラッグはこの要素の高さを変える（要素の中心を保つので対称に広がる）。
  // 指定しなければ要素自身の高さと上端位置を変える。
  heightTarget?: () => HTMLElement | null;
  // CSS 側の max-*（含む領域基準で viewport 内に収まるもの）をそのまま使う。
  keepMax?: boolean;
};

/**
 * 要素の上下左右の辺・角をドラッグしてサイズ変更できるようにし、結果を localStorage に保存する。
 * 左右の辺は中央固定の要素を前提に、反対側の辺も同じだけ動く。
 * 復元は `usePersistedSize(..., { restoreOnly: true })` と併用する（ここでは上端位置のみ復元する）。
 */
export function useEdgeResize(key: PanelKey, options: Options = {}) {
  const cleanup = useRef<(() => void) | null>(null);
  const heightTarget = useRef(options.heightTarget);
  heightTarget.current = options.heightTarget;
  const keepMax = options.keepMax ?? false;

  return useCallback(
    (el: HTMLElement | null) => {
      cleanup.current?.();
      cleanup.current = null;
      if (!el) return;

      const isMobile = () => window.innerWidth <= MOBILE_MAX_WIDTH;
      const parentBounds = () => {
        const parent = el.offsetParent as HTMLElement | null;
        const height = parent?.clientHeight ?? window.innerHeight;
        return { top: PARENT_MARGIN, bottom: height - PARENT_MARGIN };
      };

      // 自前の高さ・上端位置を持つ要素だけ、保存した上端位置を親の範囲に収めて反映する。
      const applyTop = () => {
        if (heightTarget.current) return;
        const saved = loadPanelSizes()[key];
        if (saved?.top === undefined || saved.height === undefined) return;
        el.style.top = `${clampTop(saved.top, el.offsetHeight, parentBounds())}px`;
      };
      applyTop();
      window.addEventListener("resize", applyTop);

      const findEdges = (e: PointerEvent): Edge[] => {
        const rect = el.getBoundingClientRect();
        let edges = detectEdges(rect, e.clientX, e.clientY, EDGE_ZONE);
        if (isMobile()) {
          edges = edges.filter((edge) => edge === "top" || edge === "bottom");
        }
        // 縦スクロールバーが右端にあるときは、スクロールバー操作を優先する。
        const hasScrollbar =
          el.offsetWidth - el.clientWidth > 2 &&
          el.scrollHeight > el.clientHeight;
        if (hasScrollbar) edges = edges.filter((edge) => edge !== "right");
        return edges;
      };

      let drag: {
        edges: Edge[];
        pointerId: number;
        x: number;
        y: number;
        width: number;
        height: number;
        top: number;
        reserved: number;
        target: HTMLElement;
        result: { width?: number; height?: number; top?: number };
      } | null = null;

      const onHover = (e: PointerEvent) => {
        if (drag) return;
        el.style.cursor = edgeCursor(findEdges(e));
      };

      const onDown = (e: PointerEvent) => {
        if (e.button !== 0) return;
        const edges = findEdges(e);
        if (edges.length === 0) return;
        const target = heightTarget.current?.() ?? el;
        const reserved =
          target === el
            ? 0
            : Math.max(0, el.offsetHeight - target.offsetHeight);
        e.preventDefault();
        el.setPointerCapture(e.pointerId);
        drag = {
          edges,
          pointerId: e.pointerId,
          x: e.clientX,
          y: e.clientY,
          width: el.offsetWidth,
          height: target.offsetHeight,
          top: el.offsetTop,
          reserved,
          target,
          result: {},
        };
        // 固定の max-*/flex が上限にならないよう、現在の px 値で固定して viewport 由来の上限へ置き換える。
        const horizontal = edges.some(
          (edge) => edge === "left" || edge === "right",
        );
        const vertical = edges.some(
          (edge) => edge === "top" || edge === "bottom",
        );
        if (horizontal) {
          el.style.width = `${drag.width}px`;
          if (!keepMax) el.style.maxWidth = maxPanelSizeCss("width");
        }
        if (vertical) {
          target.style.height = `${drag.height}px`;
          if (!keepMax) {
            target.style.maxHeight = maxPanelSizeCss("height", reserved);
          }
          // 親に収まらないときは縮められるようにする（ダイアログのフッタが切れないように）。
          target.style.flex = target === el ? "none" : "0 1 auto";
        }
      };

      const onMove = (e: PointerEvent) => {
        if (!drag || e.pointerId !== drag.pointerId) return;
        const symmetricY = drag.target !== el;
        const next = resizeByEdges(
          { width: drag.width, height: drag.height, top: drag.top },
          drag.edges,
          e.clientX - drag.x,
          e.clientY - drag.y,
          {
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight,
            reservedHeight: drag.reserved,
            symmetricY,
            bounds: symmetricY ? undefined : parentBounds(),
          },
        );
        const horizontal = drag.edges.some(
          (edge) => edge === "left" || edge === "right",
        );
        const vertical = drag.edges.some(
          (edge) => edge === "top" || edge === "bottom",
        );
        if (horizontal) {
          el.style.width = `${next.width}px`;
          drag.result.width = next.width;
        }
        if (vertical) {
          drag.target.style.height = `${next.height}px`;
          drag.result.height = next.height;
          if (!symmetricY) {
            el.style.top = `${next.top}px`;
            drag.result.top = next.top;
          }
        }
      };

      const onEnd = (e: PointerEvent) => {
        if (!drag || e.pointerId !== drag.pointerId) return;
        const { result, target } = drag;
        drag = null;
        // 親に収まるよう縮んでいる場合があるので、実際の高さを保存する。
        if (result.height !== undefined) result.height = target.offsetHeight;
        el.style.cursor = "";
        if (Object.keys(result).length === 0) return;
        savePanelSize(key, { ...loadPanelSizes()[key], ...result });
      };

      el.addEventListener("pointermove", onHover);
      el.addEventListener("pointerdown", onDown);
      el.addEventListener("pointermove", onMove);
      el.addEventListener("pointerup", onEnd);
      el.addEventListener("pointercancel", onEnd);
      cleanup.current = () => {
        window.removeEventListener("resize", applyTop);
        el.removeEventListener("pointermove", onHover);
        el.removeEventListener("pointerdown", onDown);
        el.removeEventListener("pointermove", onMove);
        el.removeEventListener("pointerup", onEnd);
        el.removeEventListener("pointercancel", onEnd);
      };
    },
    [key, keepMax],
  );
}
