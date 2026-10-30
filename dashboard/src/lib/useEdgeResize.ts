"use client";

import { useCallback, useRef } from "react";
import { clampTop, parseEdges, resizeByEdges, type Edge } from "./edgeResize";
import {
  loadPanelSizes,
  maxPanelSizeCss,
  savePanelSize,
  type PanelKey,
} from "./panelSizes";

// BottomNav に切り替わる幅。この幅以下では左右の辺のリサイズを無効にする。
const MOBILE_MAX_WIDTH = 640;

type Options = {
  // 指定すると、上下の辺のドラッグはこの要素の高さを変える（要素の中心を保つので対称に広がる）。
  // 指定しなければ要素自身の高さと上端位置を変える。
  heightTarget?: () => HTMLElement | null;
  // CSS 側の max-*（含む領域基準で viewport 内に収まるもの）をそのまま使う。
  keepMax?: boolean;
};

type Drag = {
  edges: Edge[];
  horizontal: boolean;
  vertical: boolean;
  pointerId: number;
  x: number;
  y: number;
  width: number;
  height: number;
  top: number;
  reserved: number;
  target: HTMLElement;
  // 最初に動いたときにインラインの固定値へ切り替えたか。クリックだけではスタイルを変えない。
  fixed: boolean;
  result: { width?: number; height?: number; top?: number };
};

/**
 * 要素内の `EdgeHandles`（`data-edge` を持つ要素）をドラッグして、上下左右の辺・角でサイズ変更できるようにし、
 * 結果を localStorage に保存する。左右の辺は中央固定の要素を前提に、反対側の辺も同じだけ動く。
 * 復元は `usePersistedSize(..., { restoreOnly: true })` と併用する（ここでは上端位置のみ復元する）。
 * 返り値は対象要素に付ける callback ref。再レンダーで呼び直されないよう、安定した参照で渡すこと。
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

      let drag: Drag | null = null;
      const isMobile = () => window.innerWidth <= MOBILE_MAX_WIDTH;
      // 親の中で上下に空ける余白は、要素の CSS（bottom）から読む。
      const parentBounds = () => {
        const parent = el.offsetParent as HTMLElement | null;
        const height = parent?.clientHeight ?? window.innerHeight;
        const margin = parseFloat(getComputedStyle(el).bottom) || 0;
        return { top: margin, bottom: height - margin };
      };

      // 自前の高さ・上端位置を持つ要素だけ、保存した上端位置を親の範囲に収めて反映する。
      const applyTop = () => {
        if (drag || heightTarget.current) return;
        const saved = loadPanelSizes()[key];
        if (saved?.top === undefined || saved.height === undefined) return;
        el.style.top = `${clampTop(saved.top, el.offsetHeight, parentBounds())}px`;
      };
      applyTop();
      window.addEventListener("resize", applyTop);

      const onDown = (e: PointerEvent) => {
        if (e.button !== 0) return;
        const handle = (e.target as Element).closest<HTMLElement>(
          "[data-edge]",
        );
        if (!handle || !el.contains(handle)) return;
        let edges = parseEdges(handle.dataset.edge);
        if (isMobile()) {
          edges = edges.filter((edge) => edge === "top" || edge === "bottom");
        }
        if (edges.length === 0) return;
        const target = heightTarget.current?.() ?? el;
        e.preventDefault();
        el.setPointerCapture(e.pointerId);
        drag = {
          edges,
          horizontal: edges.some((edge) => edge === "left" || edge === "right"),
          vertical: edges.some((edge) => edge === "top" || edge === "bottom"),
          pointerId: e.pointerId,
          x: e.clientX,
          y: e.clientY,
          width: el.offsetWidth,
          height: target.offsetHeight,
          top: el.offsetTop,
          reserved:
            target === el
              ? 0
              : Math.max(0, el.offsetHeight - target.offsetHeight),
          target,
          fixed: false,
          result: {},
        };
      };

      // 固定の max-*/flex が上限にならないよう、現在の px 値で固定して viewport 由来の上限へ置き換える。
      const fixStyles = (d: Drag) => {
        d.fixed = true;
        if (d.horizontal) {
          el.style.width = `${d.width}px`;
          if (!keepMax) el.style.maxWidth = maxPanelSizeCss("width");
        }
        if (d.vertical) {
          d.target.style.height = `${d.height}px`;
          if (!keepMax) {
            d.target.style.maxHeight = maxPanelSizeCss("height", d.reserved);
          }
          // 親に収まらないときは縮められるようにする（ダイアログのフッタが切れないように）。
          d.target.style.flex = d.target === el ? "none" : "0 1 auto";
        }
      };

      const onMove = (e: PointerEvent) => {
        if (!drag || e.pointerId !== drag.pointerId) return;
        const dx = e.clientX - drag.x;
        const dy = e.clientY - drag.y;
        if (!drag.fixed) {
          if (dx === 0 && dy === 0) return;
          fixStyles(drag);
        }
        const symmetricY = drag.target !== el;
        const next = resizeByEdges(
          { width: drag.width, height: drag.height, top: drag.top },
          drag.edges,
          dx,
          dy,
          {
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight,
            reservedHeight: drag.reserved,
            symmetricY,
            bounds: symmetricY ? undefined : parentBounds(),
          },
        );
        if (drag.horizontal) {
          el.style.width = `${next.width}px`;
          drag.result.width = next.width;
        }
        if (drag.vertical) {
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
        if (Object.keys(result).length === 0) return;
        // 親に収まるよう縮んでいる場合があるので、実際の高さを保存する。
        if (result.height !== undefined) result.height = target.offsetHeight;
        savePanelSize(key, { ...loadPanelSizes()[key], ...result });
      };

      el.addEventListener("pointerdown", onDown);
      el.addEventListener("pointermove", onMove);
      el.addEventListener("pointerup", onEnd);
      el.addEventListener("pointercancel", onEnd);
      cleanup.current = () => {
        window.removeEventListener("resize", applyTop);
        el.removeEventListener("pointerdown", onDown);
        el.removeEventListener("pointermove", onMove);
        el.removeEventListener("pointerup", onEnd);
        el.removeEventListener("pointercancel", onEnd);
      };
    },
    [key, keepMax],
  );
}
